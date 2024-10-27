import streamlit as st
import google.generativeai as genai
import json
import os
import datetime
import time
import random
import re

# Configure page layout
st.set_page_config(layout="wide", page_title="Personalized Learning Platform", initial_sidebar_state="expanded")

# Initialize session state
def initialize_session_state():
    if 'user_authenticated' not in st.session_state:
        st.session_state.user_authenticated = False
    if 'conversations' not in st.session_state:
        st.session_state.conversations = {}
    if 'tests' not in st.session_state:
        st.session_state.tests = {}
    if 'flashcards' not in st.session_state:
        st.session_state.flashcards = {}
    if 'gemini_api_key' not in st.session_state:
        st.session_state.gemini_api_key = None
    if 'user_points' not in st.session_state:
        st.session_state.user_points = 0
    if 'current_course' not in st.session_state:
        st.session_state.current_course = None

initialize_session_state()

# Function to authenticate user
def authenticate(username, password):
    return username == "user" and password == "pass"

# Function to query the Gemini API
def query_gemini_api(prompt, api_key, max_retries=3):
    genai.configure(api_key='AIzaSyC3faCZn9_0Kj_Aw7pOhw8jqGndbYiTH8M')
    model = genai.GenerativeModel('gemini-1.5-pro')
    
    for attempt in range(max_retries):
        try:
            response = model.generate_content(prompt)
            if response and response.text:
                return response.text
        except Exception as e:
            if attempt == max_retries - 1:
                raise ValueError(f"Error querying Gemini API after {max_retries} attempts: {str(e)}")
            time.sleep(2 ** attempt)  # Exponential backoff
    
    raise ValueError("No valid response from the Gemini API")

# Function to generate a study plan
def generate_study_plan(language, time_frame, level, api_key):
    prompt = f"""
    Create a {time_frame}-day course plan for learning {language} programming at {level} level. 
    Provide a daily topic breakdown in the following format:
    
    1. Topic 1
    2. Topic 2
    3. Topic 3
    ...
    {time_frame}. Topic {time_frame}
    
    Ensure each topic is concise (1-5 words) and follows a logical progression.
    If you reach the end of your response before completing all {time_frame} topics, end with 'CONTINUE' on a new line.
    When all {time_frame} topics are listed, end with 'COMPLETE' on a new line.
    """
    
    full_response = ""
    while "COMPLETE" not in full_response:
        response = query_gemini_api(prompt if not full_response else "Continue the list", api_key)
        full_response += response
        if "CONTINUE" not in full_response and "COMPLETE" not in full_response:
            full_response += "\nCONTINUE\n"
    
    # Extract topics
    topics = re.findall(r'\d+\.\s(.+)', full_response)
    return topics[:time_frame]  # Ensure we only return the requested number of topics

# Function to explain the daily topic
def explain_topic(topic, language, api_key):
    prompt = f"""
    Provide an in-depth explanation of '{topic}' in {language} programming. Include:
    1. Detailed concept explanation
    2. Code examples
    3. Best practices
    4. Common pitfalls
    5. Related LeetCode problems with explanations
    6. Additional resources for further learning

    Format your response using Markdown for better readability.
    """
    response = query_gemini_api(prompt, api_key)
    return response.strip()

# Function to save the study plan and session data
def save_session_data(language, data):
    with open(f"{language}_session.json", "w") as f:
        json.dump(data, f)

# Function to load the study plan and session data
def load_session_data(language):
    if os.path.exists(f"{language}_session.json"):
        with open(f"{language}_session.json", "r") as f:
            return json.load(f)
    return None

# Load all session data on startup
def load_all_sessions():
    sessions = {}
    for file in os.listdir():
        if file.endswith("_session.json"):
            language = file.replace("_session.json", "")
            sessions[language] = load_session_data(language)
    return sessions

# Function to generate test questions

def generate_test_questions(language, topics, api_key):
    prompt = f"""
    Generate 10 multiple-choice questions to test understanding of the following topics in {language}: {', '.join(topics)}. 
    Format each question as follows:

    Q: [question]
    A) [option]
    B) [option]
    C) [option]
    D) [option]
    Correct: [letter]
    Explanation: [brief explanation of the correct answer]

    Ensure questions cover a range of difficulty levels and aspects of the topics.
    """
    response = query_gemini_api(prompt, api_key)
    return parse_test_questions(response)

def parse_test_questions(response):
    questions = []
    current_question = {}
    for line in response.split('\n'):
        line = line.strip()
        if line.startswith('Q:'):
            if current_question:
                if 'options' in current_question and 'correct' in current_question:
                    questions.append(current_question)
                current_question = {'question': line[2:].strip(), 'options': []}
        elif line.startswith(('A)', 'B)', 'C)', 'D)')):
            current_question['options'].append(line[3:].strip())
        elif line.startswith('Correct:'):
            current_question['correct'] = line.split(':')[1].strip()
        elif line.startswith('Explanation:'):
            current_question['explanation'] = line.split(':', 1)[1].strip()
    
    if current_question and 'options' in current_question and 'correct' in current_question:
        questions.append(current_question)
    
    # Validate and filter questions
    valid_questions = []
    for q in questions:
        if len(q['options']) == 4 and q['correct'] in 'ABCD' and len(q['correct']) == 1:
            valid_questions.append(q)
    
    return valid_questions

def create_new_test(language):
    st.subheader(f"Create New Test for {language}")
    
    if language not in st.session_state.conversations:
        st.error(f"No course data found for {language}. Please create a course first.")
        return

    session_data = st.session_state.conversations[language]
    current_day = session_data.get('current_day', 1)
    study_plan = session_data.get('study_plan', [])
    
    if not study_plan:
        st.error(f"No study plan found for {language}. Please recreate the course.")
        return

    # Retrieving recent topics based on current day
    recent_topics = study_plan[max(0, current_day-3):current_day]
    
    if not recent_topics:
        st.warning("Not enough topics covered yet to create a test. Please progress further in the course.")
        return

    with st.spinner("Generating test questions..."):
        try:
            questions = generate_test_questions(language, recent_topics, st.session_state.gemini_api_key)
            if not questions:
                st.error("Failed to generate valid questions. Please try again.")
                return
            
            test_number = len(st.session_state.tests.get(language, [])) + 1
            new_test = {
                'number': test_number,
                'questions': questions,
                'user_answers': {},
                'score': 0
            }
            if language not in st.session_state.tests:
                st.session_state.tests[language] = []
            st.session_state.tests[language].append(new_test)
            st.success(f"Test {test_number} for {language} created successfully!")
            st.session_state.new_test = None
            st.session_state.current_test = (language, test_number)
            st.rerun()
        except Exception as e:
            st.error(f"An error occurred while creating the test: {str(e)}")
            st.write("Please try again. If the problem persists, contact support.")

# Function to generate flashcards
def generate_flashcards(language, topics, api_key):
    prompt = f"""
    Create 5 flashcards for the following topics in {language}: {', '.join(topics)}. 
    Format each flashcard as:

    Front: [concept or question]
    Back: [explanation or answer]

    Ensure the flashcards cover key concepts and potential areas of confusion.
    """
    response = query_gemini_api(prompt, api_key)
    return parse_flashcards(response)

def parse_flashcards(response):
    flashcards = []
    lines = response.strip().split('\n')
    current_card = {}
    for line in lines:
        if line.startswith('Front:'):
            if current_card:
                flashcards.append(current_card)
            current_card = {'front': line[6:].strip()}
        elif line.startswith('Back:'):
            current_card['back'] = line[5:].strip()
    if current_card:
        flashcards.append(current_card)
    return flashcards

# Login page
def login_page():
    st.title("Login")
    username = st.text_input("Username", key="login_username")
    password = st.text_input("Password", type="password", key="login_password")
    if st.button("Login", key="login_button"):
        if authenticate(username, password):
            st.session_state.user_authenticated = True
            st.success("Logged in successfully!")
            st.rerun()
        else:
            st.error("Invalid credentials")

# Main application
def main_app():
    # Top metrics with improved layout
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("📚 Total Courses", len(st.session_state.conversations), 
                 delta="Active", delta_color="normal")
    with col2:
        total_tests = sum(len(tests) for tests in st.session_state.tests.values())
        st.metric("📝 Total Tests", total_tests, 
                 delta="Available", delta_color="normal")
    with col3:
        completed_tests = sum(
            sum(1 for test in tests if test.get('score', 'Not taken') != 'Not taken')
            for tests in st.session_state.tests.values()
        )
        st.metric("✅ Completed Tests", completed_tests,
                 delta=f"{completed_tests}/{total_tests}", delta_color="normal")
    with col4:
        total_flashcards = sum(len(cards) for cards in st.session_state.flashcards.values())
        st.metric("🗂 Total Flashcards", total_flashcards, 
                 delta="Created", delta_color="normal")
    
    st.markdown("""
        <h1 style='text-align: center; color: #1f77b4; padding: 20px;'>
            🎓 Personalized Learning Platform
        </h1>
    """, unsafe_allow_html=True)
    
    # Sidebar with improved visual hierarchy
    with st.sidebar:
        st.markdown("# 📚 Menu")
        
        # Create larger clickable areas for menu items using containers
        menu_options = ["🏠 Home", "💻 Coding Courses", "📝 Tests", "🗂 Flashcards"]
        menu = None
        
        # Create a container for each menu option
        for option in menu_options:
            # Use columns to create a wider clickable area
            col1, padding = st.columns([4, 1])
            with col1:
                # Create a container for the menu item
                menu_container = st.container()
                with menu_container:
                    if st.button(option, key=f"menu_{option}", use_container_width=True):
                        menu = option
                        st.session_state.current_menu = option
        
        menu = st.session_state.get('current_menu', "🏠 Home")
        
        st.markdown("---")
        
        if "Coding Courses" in menu:
            st.markdown("### 💻 Coding Courses")
            for lang in st.session_state.conversations:
                # Create a container for each course
                course_container = st.container()
                with course_container:
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        # Make the entire container clickable
                        if st.button(f"📘 {lang}", 
                                   key=f"course_{lang}",
                                   use_container_width=True,
                                   type="primary" if st.session_state.get('current_course') == lang else "secondary"):
                            st.session_state.current_course = lang
                            st.rerun()
                    with col2:
                        st.markdown(f"<p style='text-align: center;'>{len(st.session_state.conversations[lang])} lessons</p>", 
                                  unsafe_allow_html=True)
            
            st.markdown("---")
            # Create a container for the new course button
            new_course_container = st.container()
            with new_course_container:
                if st.button("➕ New Course", 
                            key="new_course_button",
                            use_container_width=True,
                            type="secondary"):
                    st.session_state.new_course = True
                    st.rerun()
        
        elif "Tests" in menu:
            st.markdown("### 📝 Tests")
            for lang in st.session_state.conversations:
                with st.expander(f"📚 {lang}", expanded=True):
                    lang_tests = st.session_state.tests.get(lang, [])
                    completed_lang_tests = sum(1 for test in lang_tests if test.get('score', 'Not taken') != 'Not taken')
                    st.markdown(f"Completed: {completed_lang_tests}/{len(lang_tests)}")
                    
                    for test in lang_tests:
                        # Create a container for each test
                        test_container = st.container()
                        with test_container:
                            col1, col2 = st.columns([3, 1])
                            with col1:
                                button_type = "primary" if st.session_state.get('current_test') == (lang, test['number']) else "secondary"
                                if st.button(f"Test {test['number']}", 
                                           key=f"test_{lang}_{test['number']}", 
                                           use_container_width=True,
                                           type=button_type):
                                    st.session_state.current_test = (lang, test['number'])
                                    st.rerun()
                            with col2:
                                score = test.get('score', 'Not taken')
                                st.write(score)
                    
                    # Create a container for the new test button
                    new_test_container = st.container()
                    with new_test_container:
                        if st.button("➕ New Test", 
                                   key=f"new_test_{lang}", 
                                   use_container_width=True,
                                   type="secondary"):
                            st.session_state.new_test = lang
                            st.rerun()
        
        elif "Flashcards" in menu:
            st.markdown("### 🗂 Flashcards")
            for lang in st.session_state.flashcards:
                # Create a container for each flashcard deck
                flashcard_container = st.container()
                with flashcard_container:
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        button_type = "primary" if st.session_state.get('current_flashcards') == lang else "secondary"
                        if st.button(f"📑 {lang}", 
                                   key=f"flashcards_{lang}", 
                                   use_container_width=True,
                                   type=button_type):
                            st.session_state.current_flashcards = lang
                            st.rerun()
                    with col2:
                        card_count = len(st.session_state.flashcards[lang])
                        st.write(f"{card_count} cards")
    
    # Main content area with enhanced container
    main_container = st.container()
    with main_container:
        if "Home" in menu:
            display_home()
        elif "Coding Courses" in menu:
            if hasattr(st.session_state, 'new_course') and st.session_state.new_course:
                create_new_course()
            elif st.session_state.current_course:
                display_course_content(st.session_state.current_course)
        elif "Tests" in menu:
            if hasattr(st.session_state, 'new_test'):
                create_new_test(st.session_state.new_test)
            elif hasattr(st.session_state, 'current_test'):
                display_test()
        elif "Flashcards" in menu:
            if hasattr(st.session_state, 'current_flashcards'):
                display_flashcards()
    
    st.markdown("---")
    st.markdown(
        "<p style='text-align: center;'>Made with ❤️ by Your Learning Platform</p>",
        unsafe_allow_html=True
    )
def display_home():
    st.header("Welcome to Your Personalized Learning Platform")
    st.write("Here's an overview of your progress:")
    
    for language, course_data in st.session_state.conversations.items():
        progress = (course_data['current_day'] - 1) / course_data['max_day'] * 100
        st.write(f"**{language}:** Day {course_data['current_day']} of {course_data['max_day']}")
        st.progress(progress)
    
    st.write(f"Total Points: {st.session_state.user_points}")

def create_new_course():
    # Create main container for new course creation
    main_container = st.container()
    with main_container:
        st.subheader("🎓 Create New Course")
        
        # API Key Section
        api_key_container = st.container()
        with api_key_container:
            if not st.session_state.gemini_api_key:
                col1, col2 = st.columns([3, 1])
                with col1:
                    api_key = st.text_input(
                        "🔑 Enter your Gemini API key:",
                        type="password",
                        key="api_key_input",
                        placeholder="Paste your API key here",
                        help="Your API key will be securely stored in the session"
                    )
                with col2:
                    if api_key:
                        if st.button("✅ Verify Key", use_container_width=True):
                            st.session_state.gemini_api_key = api_key
                            genai.configure(api_key=api_key)
                            st.rerun()
                
                if not api_key:
                    st.info("ℹ️ Please enter your Gemini API key to continue.")
                    return
        
        # Course Configuration Section
        if st.session_state.gemini_api_key:
            config_container = st.container()
            with config_container:
                # Available languages with visual organization
                all_languages = [
                    "Python", "JavaScript", "Java", "C++", "C#",
                    "Ruby", "Go", "Swift", "Kotlin", "PHP",
                    "R", "TypeScript", "Scala", "Perl",
                    "Rust", "Dart", "Haskell", "MATLAB"
                ]
                available_languages = [
                    lang for lang in all_languages 
                    if lang not in st.session_state.conversations
                ]
                
                # Create three columns for main inputs
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    language_container = st.container()
                    with language_container:
                        st.markdown("##### 💻 Programming Language")
                        language = st.selectbox(
                            "Select a programming language:",
                            available_languages,
                            key="new_course_language",
                            label_visibility="collapsed",
                            format_func=lambda x: f"📚 {x}"
                        )
                
                with col2:
                    duration_container = st.container()
                    with duration_container:
                        st.markdown("##### ⏱️ Course Duration")
                        time_frame = st.number_input(
                            "Enter the course duration (days):",
                            min_value=30,
                            max_value=365,
                            value=90,
                            key="new_course_duration",
                            label_visibility="collapsed",
                            help="Choose between 30 to 365 days"
                        )
                
                with col3:
                    level_container = st.container()
                    with level_container:
                        st.markdown("##### 📊 Difficulty Level")
                        level = st.selectbox(
                            "Select your level of study:",
                            ["Beginner", "Intermediate", "Advanced"],
                            key="new_course_level",
                            label_visibility="collapsed",
                            format_func=lambda x: f"🎯 {x}"
                        )
                
                # Summary section
                summary_container = st.container()
                with summary_container:
                    st.markdown("---")
                    st.markdown("#### Course Summary")
                    sum_col1, sum_col2, sum_col3 = st.columns(3)
                    with sum_col1:
                        st.markdown(f"**Language:** 📚 {language}")
                    with sum_col2:
                        st.markdown(f"**Duration:** ⏱️ {time_frame} days")
                    with sum_col3:
                        st.markdown(f"**Level:** 🎯 {level}")
                
                # Action buttons
                button_container = st.container()
                with button_container:
                    st.markdown("---")
                    col1, col2, col3 = st.columns([1, 2, 1])
                    with col1:
                        if st.button("← Back", use_container_width=True):
                            st.session_state.new_course = False
                            st.rerun()
                    with col2:
                        if st.button("🚀 Generate Course", key="generate_course_button", use_container_width=True, type="primary"):
                            progress_container = st.container()
                            with progress_container:
                                with st.spinner("🔄 Generating your personalized course content..."):
                                    try:
                                        study_plan = generate_study_plan(
                                            language,
                                            time_frame,
                                            level,
                                            st.session_state.gemini_api_key
                                        )
                                        
                                        if study_plan:
                                            session_data = {
                                                "study_plan": study_plan,
                                                "start_date": datetime.datetime.now().strftime("%Y-%m-%d"),
                                                "current_day": 1,
                                                "max_day": time_frame,
                                                "level": level
                                            }
                                            st.session_state.conversations[language] = session_data
                                            save_session_data(language, session_data)
                                            
                                            success_container = st.container()
                                            with success_container:
                                                st.success(f"🎉 Course for {language} created successfully!")
                                                st.balloons()
                                            
                                            st.session_state.new_course = False
                                            st.session_state.current_course = language
                                            st.rerun()
                                            
                                    except Exception as e:
                                        error_container = st.container()
                                        with error_container:
                                            st.error(f"❌ An error occurred: {str(e)}")
                                            st.info("Please try again or contact support if the issue persists.")
    
def display_course_content(language):
    session_data = st.session_state.conversations[language]
    study_plan = session_data['study_plan']
    current_day = session_data['current_day']
    max_day = session_data['max_day']
    
    st.header(f"Course Content for {language}")
    st.write(f"Current Progress: Day {current_day} of {max_day}")
    
    if 0 <= current_day - 1 < len(study_plan):
        topic = study_plan[current_day - 1]
        st.subheader(f"Day {current_day}: {topic}")
        
        if st.button("Explain Today's Topic", key="explain_topic_button"):
            with st.spinner("Generating explanation..."):
                try:
                    explanation = explain_topic(topic, language, st.session_state.gemini_api_key)
                    if explanation:
                        st.markdown(explanation)
                except Exception as e:
                    st.error(f"Error explaining topic: {str(e)}")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Previous Day", key="prev_day_button", disabled=current_day <= 1):
                session_data['current_day'] -= 1
                save_session_data(language, session_data)
                st.rerun()
        with col2:
            if st.button("Next Day", key="next_day_button", disabled=current_day >= max_day):
                session_data['current_day'] += 1
                save_session_data(language, session_data)
                st.rerun()
    else:
        st.write("Course completed! You can review previous topics or start a new course.")

def display_test():
    language, test_number = st.session_state.current_test
    test_data = next(test for test in st.session_state.tests[language] if test['number'] == test_number)
    
    st.subheader(f"{language} - Test {test_number}")
    
    if 'current_question' not in st.session_state:
        st.session_state.current_question = 0
    
    if st.session_state.current_question < len(test_data['questions']):
        question = test_data['questions'][st.session_state.current_question]
        st.write(f"Question {st.session_state.current_question + 1}: {question['question']}")
        
        user_answer = st.radio("Select your answer:", question['options'], key=f"q_{st.session_state.current_question}")
        
        if st.button("Submit Answer", key="submit_answer"):
            test_data['user_answers'][st.session_state.current_question] = user_answer
            correct_answer = question['options'][ord(question['correct']) - ord('A')]
            if user_answer == correct_answer:
                st.success("Correct!")
                test_data['score'] += 1
            else:
                st.error(f"Incorrect. The correct answer is: {correct_answer}")
            st.write(f"Explanation: {question['explanation']}")
            
            st.session_state.current_question += 1
            if st.session_state.current_question < len(test_data['questions']):
                st.rerun()
            else:
                st.success("Test completed!")
                st.write(f"Your score: {test_data['score']}/{len(test_data['questions'])}")
                
                incorrect_topics = [q['question'].split()[0] for i, q in enumerate(test_data['questions']) 
                                    if test_data['user_answers'].get(i) != question['options'][ord(question['correct']) - ord('A')]]
                
                if incorrect_topics:
                    st.write("Topics to review:")
                    st.write(", ".join(set(incorrect_topics)))
                    
                    if st.button("Generate Flashcards for Review", key="generate_flashcards"):
                        generate_review_flashcards(language, list(set(incorrect_topics)))
                
                if st.button("Retake Test", key="retake_test"):
                    test_data['user_answers'] = {}
                    test_data['score'] = 0
                    st.session_state.current_question = 0
                    st.rerun()
    else:
        st.write("Test completed. You can retake the test or go back to the course content.")

def generate_review_flashcards(language, topics):
    with st.spinner("Generating flashcards..."):
        try:
            flashcards = generate_flashcards(language, topics, st.session_state.gemini_api_key)
            if language not in st.session_state.flashcards:
                st.session_state.flashcards[language] = []
            st.session_state.flashcards[language].extend(flashcards)
            st.success("Flashcards generated successfully!")
            st.session_state.current_flashcards = language
            st.rerun()
        except Exception as e:
            st.error(f"An error occurred: {str(e)}")

def display_flashcards():
    language = st.session_state.current_flashcards
    flashcards = st.session_state.flashcards[language]
    
    st.subheader(f"Flashcards for {language}")
    
    if 'current_card' not in st.session_state:
        st.session_state.current_card = 0
    
    if flashcards:
        card = flashcards[st.session_state.current_card]
        
        col1, col2 = st.columns(2)
        with col1:
            st.write("Front:")
            st.write(card['front'])
        with col2:
            if st.button("Reveal Answer", key="reveal_answer"):
                st.write("Back:")
                st.write(card['back'])
        
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("Previous Card", key="prev_card", disabled=st.session_state.current_card <= 0):
                st.session_state.current_card -= 1
                st.rerun()
        with col2:
            if st.button("Next Card", key="next_card", disabled=st.session_state.current_card >= len(flashcards) - 1):
                st.session_state.current_card += 1
                st.rerun()
        with col3:
            if st.button("Shuffle", key="shuffle_cards"):
                random.shuffle(flashcards)
                st.session_state.current_card = 0
                st.rerun()
    else:
        st.write("No flashcards available for this language.")

# User progress tracking
def update_user_progress(language, day_completed):
    if 'progress' not in st.session_state:
        st.session_state.progress = {}
    if language not in st.session_state.progress:
        st.session_state.progress[language] = set()
    st.session_state.progress[language].add(day_completed)
    save_progress(language)

def save_progress(language):
    progress_file = f"{language}_progress.json"
    with open(progress_file, 'w') as f:
        json.dump(list(st.session_state.progress[language]), f)

def load_progress(language):
    progress_file = f"{language}_progress.json"
    if os.path.exists(progress_file):
        with open(progress_file, 'r') as f:
            return set(json.load(f))
    return set()

# Gamification elements
def award_points(points):
    st.session_state.user_points += points
    st.success(f"You earned {points} points!")

def display_achievements():
    st.sidebar.write(f"Total Points: {st.session_state.user_points}")
    
    achievements = [
        ("Beginner", 100, "Started your coding journey"),
        ("Intermediate", 500, "Making good progress"),
        ("Advanced", 1000, "Becoming a coding expert"),
        ("Master", 5000, "True coding master")
    ]
    
    for title, points, description in achievements:
        if st.session_state.user_points >= points:
            st.sidebar.write(f"🏆 {title}: {description}")

# Main execution
if __name__ == "__main__":
    if not st.session_state.user_authenticated:
        login_page()
    else:
        main_app()
        display_achievements()

# Logout functionality
if st.sidebar.button("Logout", key="logout"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# Error handling and graceful degradation
try:
    # Your main application logic here
    pass
except Exception as e:
    st.error(f"An unexpected error occurred: {str(e)}")
    st.write("Please try refreshing the page or contact support if the issue persists.")

# Performance optimization
@st.cache_data
def load_language_data(language):
    # Load and cache language-specific data
    pass

# Accessibility features
st.markdown("""
<style>
    body {
        font-family: Arial, sans-serif;
        line-height: 1.6;
    }
    .stButton>button {
        font-size: 16px;
        padding: 10px 20px;
    }
</style>
""", unsafe_allow_html=True)
