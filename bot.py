from dotenv import load_dotenv
load_dotenv()

import discord
from discord.ext import commands
from openai import AsyncOpenAI
import os
from pathlib import Path
import PyPDF2
from typing import List, Dict, Optional
import json

# Bot configuration
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# OpenAI setup
client = AsyncOpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# User profile system
class UserProfileManager:
    def __init__(self, base_path: str = "./user_data"):
        self.base_path = Path(base_path)
        self.profiles_file = self.base_path / "profiles.json"
        self._ensure_base_folder()
        self.profiles = self._load_profiles()
    
    def _ensure_base_folder(self):
        """Create base folder structure"""
        self.base_path.mkdir(parents=True, exist_ok=True)
        if not self.profiles_file.exists():
            with open(self.profiles_file, 'w') as f:
                json.dump({}, f)
    
    def _load_profiles(self) -> dict:
        """Load user profiles from JSON"""
        try:
            with open(self.profiles_file, 'r') as f:
                return json.load(f)
        except:
            return {}
    
    def _save_profiles(self):
        """Save profiles to JSON"""
        with open(self.profiles_file, 'w') as f:
            json.dump(self.profiles, f, indent=2)
    
    def get_user_profile(self, user_id: int) -> dict:
        """Get user's profile, create if doesn't exist"""
        user_id_str = str(user_id)
        if user_id_str not in self.profiles:
            self.profiles[user_id_str] = {
                "subjects": {},
                "active_subject": None
            }
            self._save_profiles()
        return self.profiles[user_id_str]
    
    def create_subject(self, user_id: int, subject_name: str, game: str = "popular video games") -> bool:
        """Create a new subject for user"""
        profile = self.get_user_profile(user_id)
        subject_key = subject_name.lower().replace(" ", "_")
        
        if subject_key in profile["subjects"]:
            return False
        
        # Create folder structure
        subject_path = self.base_path / str(user_id) / subject_key
        (subject_path / "lectures").mkdir(parents=True, exist_ok=True)
        (subject_path / "practice_tests").mkdir(parents=True, exist_ok=True)
        
        profile["subjects"][subject_key] = {
            "name": subject_name,
            "game": game,
            "created": True,
            "question_bank": []
        }
        
        # Set as active if it's the first subject
        if profile["active_subject"] is None:
            profile["active_subject"] = subject_key
        
        self._save_profiles()
        return True
    
    def get_subject_path(self, user_id: int, subject_key: str) -> Optional[Path]:
        """Get path to subject folder"""
        return self.base_path / str(user_id) / subject_key
    
    def set_active_subject(self, user_id: int, subject_name: str) -> bool:
        """Set active subject for user"""
        profile = self.get_user_profile(user_id)
        subject_key = subject_name.lower().replace(" ", "_")
        
        if subject_key not in profile["subjects"]:
            return False
        
        profile["active_subject"] = subject_key
        self._save_profiles()
        return True
    
    def get_active_subject(self, user_id: int) -> Optional[dict]:
        """Get user's active subject info"""
        profile = self.get_user_profile(user_id)
        if profile["active_subject"] is None:
            return None
        
        subject_key = profile["active_subject"]
        subject_info = profile["subjects"][subject_key]
        subject_info["key"] = subject_key
        return subject_info
    
    def set_subject_game(self, user_id: int, subject_key: str, game: str):
        """Set game preference for a subject"""
        profile = self.get_user_profile(user_id)
        if subject_key in profile["subjects"]:
            profile["subjects"][subject_key]["game"] = game
            self._save_profiles()
    
    def add_question_to_bank(self, user_id: int, subject_key: str, question: str) -> bool:
        """Add a question to the subject's question bank"""
        profile = self.get_user_profile(user_id)
        if subject_key in profile["subjects"]:
            if "question_bank" not in profile["subjects"][subject_key]:
                profile["subjects"][subject_key]["question_bank"] = []
            profile["subjects"][subject_key]["question_bank"].append(question)
            self._save_profiles()
            return True
        return False
    
    def get_question_bank(self, user_id: int, subject_key: str) -> list:
        """Get all questions from the question bank"""
        profile = self.get_user_profile(user_id)
        if subject_key in profile["subjects"]:
            return profile["subjects"][subject_key].get("question_bank", [])
        return []
    
    def remove_question_from_bank(self, user_id: int, subject_key: str, index: int) -> bool:
        """Remove a question from the bank by index"""
        profile = self.get_user_profile(user_id)
        if subject_key in profile["subjects"]:
            questions = profile["subjects"][subject_key].get("question_bank", [])
            if 0 <= index < len(questions):
                questions.pop(index)
                profile["subjects"][subject_key]["question_bank"] = questions
                self._save_profiles()
                return True
        return False
    
    def list_subjects(self, user_id: int) -> list:
        """List all subjects for user"""
        profile = self.get_user_profile(user_id)
        return [
            {
                "key": key,
                "name": info["name"],
                "game": info["game"],
                "active": key == profile["active_subject"]
            }
            for key, info in profile["subjects"].items()
        ]
    
    def delete_subject(self, user_id: int, subject_name: str) -> bool:
        """Delete a subject"""
        profile = self.get_user_profile(user_id)
        subject_key = subject_name.lower().replace(" ", "_")
        
        if subject_key not in profile["subjects"]:
            return False
        
        # Delete folder
        import shutil
        subject_path = self.get_subject_path(user_id, subject_key)
        if subject_path.exists():
            shutil.rmtree(subject_path)
        
        # Remove from profile
        del profile["subjects"][subject_key]
        
        # Reset active subject if needed
        if profile["active_subject"] == subject_key:
            profile["active_subject"] = next(iter(profile["subjects"].keys())) if profile["subjects"] else None
        
        self._save_profiles()
        return True

profile_manager = UserProfileManager()

# Document storage structure
class DocumentManager:
    def extract_text_from_pdf(self, file_path: Path) -> str:
        """Extract text from PDF file"""
        text = ""
        try:
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
        except Exception as e:
            print(f"Error reading PDF: {e}")
        return text
    
    def get_all_lectures_with_names(self, user_id: int) -> Dict[str, str]:
        """Get all lecture content with filenames for active subject"""
        subject = profile_manager.get_active_subject(user_id)
        if not subject:
            return {}
        
        lecture_path = profile_manager.get_subject_path(user_id, subject["key"]) / "lectures"
        lectures = {}
        for pdf_file in lecture_path.glob("*.pdf"):
            filename = pdf_file.stem
            content = self.extract_text_from_pdf(pdf_file)
            lectures[filename] = f"[SOURCE: {filename}]\n{content}"
        return lectures
    
    def get_all_practice_tests_with_names(self, user_id: int) -> Dict[str, str]:
        """Get all practice test content with filenames for active subject"""
        subject = profile_manager.get_active_subject(user_id)
        if not subject:
            return {}
        
        practice_path = profile_manager.get_subject_path(user_id, subject["key"]) / "practice_tests"
        tests = {}
        for pdf_file in practice_path.glob("*.pdf"):
            filename = pdf_file.stem
            content = self.extract_text_from_pdf(pdf_file)
            tests[filename] = f"[SOURCE: {filename}]\n{content}"
        return tests
    
    async def save_attachment(self, attachment: discord.Attachment, user_id: int, folder_type: str) -> bool:
        """Save Discord attachment to appropriate folder"""
        if not attachment.filename.endswith('.pdf'):
            return False
        
        subject = profile_manager.get_active_subject(user_id)
        if not subject:
            return False
        
        target_path = profile_manager.get_subject_path(user_id, subject["key"])
        target_path = target_path / ("lectures" if folder_type == "lecture" else "practice_tests")
        file_path = target_path / attachment.filename
        
        try:
            await attachment.save(file_path)
            return True
        except Exception as e:
            print(f"Error saving attachment: {e}")
            return False
    
    def list_files(self, user_id: int, folder_type: str) -> list:
        """List files in a folder"""
        subject = profile_manager.get_active_subject(user_id)
        if not subject:
            return []
        
        folder_path = profile_manager.get_subject_path(user_id, subject["key"])
        folder_path = folder_path / ("lectures" if folder_type == "lecture" else "practice_tests")
        
        return [f.stem for f in folder_path.glob("*.pdf")]

doc_manager = DocumentManager()

# AI Teaching Assistant
class AITeacher:
    def __init__(self):
        self.teaching_styles = {
            "genz": "Explain using Gen-Z slang, memes, and relatable references. Be casual and fun.",
            "mnemonic": "Create memorable mnemonics and memory tricks using video game references.",
            "simple": "Explain in clear, simple terms with examples.",
            "detailed": "Provide comprehensive, detailed explanations with technical accuracy."
        }
    
    def get_subject_game(self, user_id: int) -> str:
        """Get game for active subject"""
        subject = profile_manager.get_active_subject(user_id)
        if not subject:
            return "popular video games"
        return subject.get("game", "popular video games")
    
    async def generate_practice_test_from_existing(self, practice_tests: Dict[str, str], 
                                                   question_bank: list, num_questions: int = 10) -> str:
        """Generate practice test by creating variations of existing test questions"""
        
        # Combine practice test content with source labels
        practice_content = "\n\n".join([f"{content[:1500]}" for content in practice_tests.values()])
        
        # Add question bank questions
        bank_questions = "\n".join([f"- {q}" for q in question_bank]) if question_bank else "No additional questions in bank"
        
        prompt = f"""You are creating a practice test with {num_questions} questions.

IMPORTANT INSTRUCTIONS:
1. Base your questions on the practice tests provided below
2. Create VARIATIONS of existing questions - don't copy them exactly, but test the same concepts
3. Include questions from the question bank if provided
4. Make questions slightly different but test the same knowledge
5. Include the question types found in the source material (multiple choice, short answer, etc.)
6. Cite which source file each question concept comes from using [Source: filename]

Practice Test Material:
{practice_content}

Additional Question Bank:
{bank_questions}

Create a well-formatted practice test with {num_questions} questions, citing sources."""
        
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful study assistant creating practice test variations from existing materials. Always cite sources."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=2000
        )
        
        return response.choices[0].message.content
    
    async def teach_lesson(self, topic: str, lecture_content: str, 
                          practice_content: str, style: str = "genz", 
                          user_id: int = None) -> str:
        """Generate a mini lesson highlighting test-relevant content with citations"""
        style_instruction = self.teaching_styles.get(style, self.teaching_styles["simple"])
        
        game_context = ""
        if style == "mnemonic" and user_id:
            game = self.get_subject_game(user_id)
            game_context = f"\nIMPORTANT: Create mnemonics and memory tricks, if possible, using references from {game}. Use characters, items, mechanics, and concepts from this game to make memorable associations. Otherwise, use another memorable mnemonic."
        
        prompt = f"""You are teaching a mini-lesson on: {topic}
        
        Teaching Style: {style_instruction}{game_context}
        
        Lecture Material (with sources):
        {lecture_content[:1500]}
        
        Practice Test Material (use this to identify what's important):
        {practice_content[:1000]}
        
        Create a focused mini-lesson that:
        1. Highlights concepts that appear in practice tests with [Source: filename] citations
        2. Explains key concepts in the requested style
        3. Provides memorable examples or mnemonics
        4. Keeps it concise (5-7 key points max)
        5. ALWAYS cite which file information comes from
        
        Make it engaging and test-focused!"""
        
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an engaging study coach who makes learning fun and effective, always citing sources with [Source: filename]."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.8,
            max_tokens=1500
        )
        
        return response.choices[0].message.content
    
    async def answer_question(self, question: str, lecture_content: str, 
                             practice_content: str, style: str = "genz",
                             user_id: int = None) -> str:
        """Answer a specific question using both lecture and practice materials with citations"""
        style_instruction = self.teaching_styles.get(style, self.teaching_styles["simple"])
        
        game_context = ""
        if style == "mnemonic" and user_id:
            game = self.get_subject_game(user_id)
            game_context = f"\nIMPORTANT: Use references from {game} to create mnemonics and memorable explanations."
        
        prompt = f"""Answer this question: {question}
        
        Style: {style_instruction}{game_context}
        
        Reference Material (with sources):
        {lecture_content[:1500]}
        
        Test Material (for context on what's important):
        {practice_content[:1000]}
        
        Provide a helpful answer that:
        1. Cites sources with [Source: filename]
        2. Is relevant to their studies and potential test questions
        3. Includes specific references or quotes when appropriate"""
        
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful study assistant who always cites sources with [Source: filename]."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1000
        )
        
        return response.choices[0].message.content

ai_teacher = AITeacher()

# Bot Commands
@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    print(f'User profile system ready')

# Subject Management Commands
@bot.command(name='newsubject')
async def new_subject(ctx, game: str = "popular video games", *, subject_name: str = ""):
    """Create a new subject with optional game preference
    Usage: !newsubject Biology
           !newsubject Pokemon Biology 101"""
    
    if not subject_name:
        if game and game != "popular video games":
            subject_name = game
            game = "popular video games"
        else:
            await ctx.send("❌ Please provide a subject name!\nUsage: `!newsubject Biology` or `!newsubject Pokemon Biology`")
            return
    
    success = profile_manager.create_subject(ctx.author.id, subject_name, game)
    
    if success:
        await ctx.send(f"✅ Created new subject: **{subject_name}**\n🎮 Mnemonic game: **{game}**\n\nThis is now your active subject! Upload materials with `!upload`")
    else:
        await ctx.send(f"❌ Subject **{subject_name}** already exists!")

@bot.command(name='subjects')
async def list_subjects(ctx):
    """List all your subjects"""
    subjects = profile_manager.list_subjects(ctx.author.id)
    
    if not subjects:
        await ctx.send("📚 You don't have any subjects yet!\nCreate one with: `!newsubject Biology`")
        return
    
    embed = discord.Embed(title="📚 Your Subjects", color=discord.Color.blue())
    
    for subj in subjects:
        status = "✅ ACTIVE" if subj["active"] else ""
        embed.add_field(
            name=f"{subj['name']} {status}",
            value=f"🎮 Game: {subj['game']}",
            inline=False
        )
    
    embed.set_footer(text="Switch subjects with: !switch <subject name>")
    await ctx.send(embed=embed)

@bot.command(name='switch')
async def switch_subject(ctx, *, subject_name: str):
    """Switch to a different subject
    Usage: !switch Biology"""
    
    success = profile_manager.set_active_subject(ctx.author.id, subject_name)
    
    if success:
        subject = profile_manager.get_active_subject(ctx.author.id)
        await ctx.send(f"✅ Switched to: **{subject['name']}**\n🎮 Game: **{subject['game']}**")
    else:
        await ctx.send(f"❌ Subject **{subject_name}** not found!\nView your subjects with `!subjects`")

@bot.command(name='setgame')
async def set_game(ctx, *, game_name: str = ""):
    """Set game preference for current subject
    Usage: !setgame Pokemon"""
    
    subject = profile_manager.get_active_subject(ctx.author.id)
    
    if not subject:
        await ctx.send("❌ No active subject! Create one with `!newsubject <name>`")
        return
    
    if not game_name:
        await ctx.send(f"🎮 Current game for **{subject['name']}**: **{subject['game']}**\n\nChange it with: `!setgame <game name>`")
        return
    
    profile_manager.set_subject_game(ctx.author.id, subject["key"], game_name)
    await ctx.send(f"🎮 Set **{subject['name']}** mnemonic game to: **{game_name}**!")

@bot.command(name='deletesubject')
async def delete_subject(ctx, *, subject_name: str):
    """Delete a subject and all its files
    Usage: !deletesubject Biology"""
    
    await ctx.send(f"⚠️ Are you sure you want to delete **{subject_name}** and ALL its files?\nType `yes` to confirm or `no` to cancel.")
    
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel
    
    try:
        msg = await bot.wait_for('message', check=check, timeout=30.0)
        
        if msg.content.lower() == 'yes':
            success = profile_manager.delete_subject(ctx.author.id, subject_name)
            if success:
                await ctx.send(f"✅ Deleted **{subject_name}** and all its files.")
            else:
                await ctx.send(f"❌ Subject **{subject_name}** not found!")
        else:
            await ctx.send("❌ Cancelled deletion.")
    except:
        await ctx.send("❌ Timed out. Deletion cancelled.")

@bot.command(name='active')
async def show_active(ctx):
    """Show your currently active subject"""
    subject = profile_manager.get_active_subject(ctx.author.id)
    
    if not subject:
        await ctx.send("❌ No active subject! Create one with `!newsubject <name>`")
        return
    
    lectures = doc_manager.list_files(ctx.author.id, "lecture")
    practices = doc_manager.list_files(ctx.author.id, "practice")
    question_count = len(subject.get("question_bank", []))
    
    embed = discord.Embed(title=f"📖 {subject['name']}", color=discord.Color.green())
    embed.add_field(name="🎮 Mnemonic Game", value=subject['game'], inline=False)
    embed.add_field(name="📚 Lectures", value=str(len(lectures)), inline=True)
    embed.add_field(name="📝 Practice Tests", value=str(len(practices)), inline=True)
    embed.add_field(name="❓ Question Bank", value=str(question_count), inline=True)
    
    await ctx.send(embed=embed)

# Question Bank Commands
@bot.command(name='addq')
async def add_question(ctx, *, question: str):
    """Add a question to the question bank
    Usage: !addq What is the powerhouse of the cell?"""
    
    subject = profile_manager.get_active_subject(ctx.author.id)
    if not subject:
        await ctx.send("❌ No active subject! Create one with `!newsubject <name>`")
        return
    
    success = profile_manager.add_question_to_bank(ctx.author.id, subject["key"], question)
    
    if success:
        count = len(profile_manager.get_question_bank(ctx.author.id, subject["key"]))
        await ctx.send(f"✅ Added question to **{subject['name']}** question bank!\nTotal questions: {count}")
    else:
        await ctx.send("❌ Failed to add question.")

@bot.command(name='questions')
async def list_questions(ctx):
    """List all questions in the question bank"""
    subject = profile_manager.get_active_subject(ctx.author.id)
    if not subject:
        await ctx.send("❌ No active subject! Create one with `!newsubject <name>`")
        return
    
    questions = profile_manager.get_question_bank(ctx.author.id, subject["key"])
    
    if not questions:
        await ctx.send(f"❓ No questions in **{subject['name']}** question bank yet!\nAdd some with `!addq <question>`")
        return
    
    embed = discord.Embed(title=f"❓ {subject['name']} - Question Bank", color=discord.Color.gold())
    
    for i, q in enumerate(questions):
        # Truncate long questions for display
        display_q = q[:100] + "..." if len(q) > 100 else q
        embed.add_field(name=f"#{i+1}", value=display_q, inline=False)
    
    embed.set_footer(text=f"Remove questions with: !removeq <number>")
    await ctx.send(embed=embed)

@bot.command(name='removeq')
async def remove_question(ctx, question_num: int):
    """Remove a question from the question bank
    Usage: !removeq 3"""
    
    subject = profile_manager.get_active_subject(ctx.author.id)
    if not subject:
        await ctx.send("❌ No active subject! Create one with `!newsubject <name>`")
        return
    
    success = profile_manager.remove_question_from_bank(ctx.author.id, subject["key"], question_num - 1)
    
    if success:
        remaining = len(profile_manager.get_question_bank(ctx.author.id, subject["key"]))
        await ctx.send(f"✅ Removed question #{question_num} from **{subject['name']}**\nRemaining questions: {remaining}")
    else:
        await ctx.send(f"❌ Question #{question_num} not found!")

# Document Management Commands
@bot.command(name='upload')
async def upload_document(ctx, doc_type: str):
    """Upload a PDF to current subject
    Usage: !upload lecture (attach PDF) or !upload practice (attach PDF)"""
    
    subject = profile_manager.get_active_subject(ctx.author.id)
    if not subject:
        await ctx.send("❌ No active subject! Create one with `!newsubject <name>`")
        return
    
    if doc_type.lower() not in ['lecture', 'practice']:
        await ctx.send("❌ Please specify either 'lecture' or 'practice'\nUsage: `!upload lecture` (with PDF attached)")
        return
    
    if not ctx.message.attachments:
        await ctx.send("❌ Please attach a PDF file to your message!")
        return
    
    attachment = ctx.message.attachments[0]
    
    if not attachment.filename.endswith('.pdf'):
        await ctx.send("❌ Please upload a PDF file!")
        return
    
    folder_name = "lectures" if doc_type.lower() == 'lecture' else "practice tests"
    await ctx.send(f"⏳ Uploading {attachment.filename} to **{subject['name']}** {folder_name}...")
    
    success = await doc_manager.save_attachment(attachment, ctx.author.id, doc_type.lower())
    
    if success:
        await ctx.send(f"✅ Successfully uploaded {attachment.filename} to **{subject['name']}** {folder_name}!")
    else:
        await ctx.send(f"❌ Failed to upload file. Please try again.")

@bot.command(name='list')
async def list_documents(ctx):
    """List all uploaded documents for current subject"""
    subject = profile_manager.get_active_subject(ctx.author.id)
    
    if not subject:
        await ctx.send("❌ No active subject! Create one with `!newsubject <name>`")
        return
    
    lectures = doc_manager.list_files(ctx.author.id, "lecture")
    practices = doc_manager.list_files(ctx.author.id, "practice")
    
    embed = discord.Embed(title=f"📚 {subject['name']} - Study Materials", color=discord.Color.blue())
    
    lecture_list = "\n".join([f"• {f}" for f in lectures]) or "No lectures uploaded"
    practice_list = "\n".join([f"• {f}" for f in practices]) or "No practice tests uploaded"
    
    embed.add_field(name="📖 Lectures", value=lecture_list, inline=False)
    embed.add_field(name="📝 Practice Tests", value=practice_list, inline=False)
    
    await ctx.send(embed=embed)

# AI Learning Commands
@bot.command(name='maketest')
async def make_test(ctx, num_questions: int = 10):
    """Generate a practice test from UPLOADED practice tests (variations)
    Usage: !maketest 15"""
    
    subject = profile_manager.get_active_subject(ctx.author.id)
    if not subject:
        await ctx.send("❌ No active subject! Create one with `!newsubject <name>`")
        return
    
    practice_tests = doc_manager.get_all_practice_tests_with_names(ctx.author.id)
    question_bank = profile_manager.get_question_bank(ctx.author.id, subject["key"])
    
    if not practice_tests and not question_bank:
        await ctx.send(f"❌ No practice tests or questions found for **{subject['name']}**!\n\n"
                      f"Upload practice tests with `!upload practice` or add questions with `!addq <question>`")
        return
    
    await ctx.send(f"⏳ Generating a {num_questions}-question practice test from uploaded materials...")
    
    try:
        test = await ai_teacher.generate_practice_test_from_existing(
            practice_tests, 
            question_bank,
            num_questions
        )
        
        chunks = [test[i:i+1900] for i in range(0, len(test), 1900)]
        
        await ctx.send(f"📝 **{subject['name']} - Practice Test:**")
        for chunk in chunks:
            await ctx.send(f"```\n{chunk}\n```")
            
    except Exception as e:
        await ctx.send(f"❌ Error generating test: {str(e)}")

@bot.command(name='teach')
async def teach_lesson(ctx, style: str = "genz", *, topic: str = ""):
    """Get a mini-lesson on a topic with source citations
    Usage: !teach genz cellular respiration
    Styles: genz, mnemonic, simple, detailed"""
    
    subject = profile_manager.get_active_subject(ctx.author.id)
    if not subject:
        await ctx.send("❌ No active subject! Create one with `!newsubject <name>`")
        return
    
    if not topic:
        await ctx.send("❌ Please provide a topic!\nUsage: `!teach genz cellular respiration`")
        return
    
    lectures = doc_manager.get_all_lectures_with_names(ctx.author.id)
    practices = doc_manager.get_all_practice_tests_with_names(ctx.author.id)
    
    if not lectures:
        await ctx.send(f"❌ No lecture materials found for **{subject['name']}**!\nUpload some with `!upload lecture`")
        return
    
    if style == "mnemonic":
        await ctx.send(f"⏳ Teaching you about **{topic}** in {style} style using **{subject['game']}** references...")
    else:
        await ctx.send(f"⏳ Teaching you about **{topic}** in {style} style...")
    
    combined_lectures = "\n\n".join(lectures.values())
    combined_practices = "\n\n".join(practices.values())
    
    try:
        lesson = await ai_teacher.teach_lesson(
            topic, 
            combined_lectures, 
            combined_practices,
            style,
            ctx.author.id
        )
        
        chunks = [lesson[i:i+1900] for i in range(0, len(lesson), 1900)]
        
        await ctx.send(f"🎓 **{subject['name']} - Mini-Lesson: {topic}**")
        for chunk in chunks:
            await ctx.send(chunk)
            
    except Exception as e:
        await ctx.send(f"❌ Error generating lesson: {str(e)}")

@bot.command(name='ask')
async def ask_question(ctx, style: str = "genz", *, question: str = ""):
    """Ask a question about your study materials with citations
    Usage: !ask genz what is mitochondria?
    Styles: genz, mnemonic, simple, detailed"""
    
    subject = profile_manager.get_active_subject(ctx.author.id)
    if not subject:
        await ctx.send("❌ No active subject! Create one with `!newsubject <n>`")
        return
    
    if not question:
        await ctx.send("❌ Please ask a question!\nUsage: `!ask genz what is mitochondria?`")
        return
    
    lectures = doc_manager.get_all_lectures_with_names(ctx.author.id)
    practices = doc_manager.get_all_practice_tests_with_names(ctx.author.id)
    
    if not lectures:
        await ctx.send(f"❌ No lecture materials found for **{subject['name']}**!\nUpload some with `!upload lecture`")
        return
    
    await ctx.send(f"⏳ Thinking...")
    
    combined_lectures = "\n\n".join(lectures.values())
    combined_practices = "\n\n".join(practices.values())
    
    try:
        answer = await ai_teacher.answer_question(
            question,
            combined_lectures,
            combined_practices,
            style,
            ctx.author.id
        )
        
        chunks = [answer[i:i+1900] for i in range(0, len(answer), 1900)]
        
        await ctx.send(f"💡 **Answer ({subject['name']}):**")
        for chunk in chunks:
            await ctx.send(chunk)
            
    except Exception as e:
        await ctx.send(f"❌ Error answering question: {str(e)}")

@bot.command(name='styles')
async def show_styles(ctx):
    """Show available teaching styles"""
    embed = discord.Embed(title="🎨 Teaching Styles", color=discord.Color.purple())
    
    embed.add_field(
        name="genz", 
        value="Casual, fun explanations with Gen-Z slang and memes", 
        inline=False
    )
    embed.add_field(
        name="mnemonic", 
        value="Memory tricks and mnemonics using video game references", 
        inline=False
    )
    embed.add_field(
        name="simple", 
        value="Clear, straightforward explanations", 
        inline=False
    )
    embed.add_field(
        name="detailed", 
        value="Comprehensive, technical explanations", 
        inline=False
    )
    
    await ctx.send(embed=embed)

@bot.command(name='commands')
async def help_command(ctx):
    """Show all commands"""
    embed = discord.Embed(
        title="🤖 Study Assistant Commands",
        description="Your AI-powered study buddy with multi-subject support!",
        color=discord.Color.green()
    )
    
    embed.add_field(
        name="📚 Subject Management",
        value="`!newsubject <name>` - Create new subject\n"
              "`!subjects` - List all subjects\n"
              "`!switch <name>` - Switch active subject\n"
              "`!active` - Show current subject\n"
              "`!deletesubject <name>` - Delete a subject",
        inline=False
    )
    
    embed.add_field(
        name="📁 File Management",
        value="`!upload <lecture|practice>` - Upload PDF (attach file)\n"
              "`!list` - List files in current subject",
        inline=False
    )
    
    embed.add_field(
        name="❓ Question Bank",
        value="`!addq <question>` - Add question to bank\n"
              "`!questions` - List all questions\n"
              "`!removeq <num>` - Remove a question",
        inline=False
    )
    
    embed.add_field(
        name="🎓 Learning Commands",
        value="`!maketest [num]` - Generate test from practice PDFs\n"
              "`!teach <style> <topic>` - Get mini-lesson\n"
              "`!ask <style> <question>` - Ask a question\n"
              "`!styles` - Show teaching styles",
        inline=False
    )
    
    embed.add_field(
        name="🎮 Personalization",
        value="`!setgame <game>` - Set game for mnemonics",
        inline=False
    )
    
    embed.set_footer(text="All responses now cite sources! Each subject has its own files, game, and question bank!")
    await ctx.send(embed=embed)

# Run the bot
if __name__ == "__main__":
    TOKEN = os.getenv('DISCORD_BOT_TOKEN')
    if not TOKEN:
        print("ERROR: DISCORD_BOT_TOKEN not found in environment variables")
    else:
        bot.run(TOKEN)