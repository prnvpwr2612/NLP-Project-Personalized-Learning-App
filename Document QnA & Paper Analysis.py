import streamlit as st
import os
import io
import base64
import PyPDF2
import docx
import google.generativeai as genai
from gtts import gTTS
import tempfile
import time

# Configure page
st.set_page_config(page_title="Research Paper Analyzer", layout="wide")

# Initialize Gemini API with retry mechanism
@st.cache_resource
def initialize_gemini_api(api_key):
    genai.configure(api_key=api_key)
    return genai.GenerativeModel('gemini-pro')

def generate_with_backoff(model, prompt, max_retries=5, initial_delay=1):
    for attempt in range(max_retries):
        try:
            time.sleep(initial_delay * (2 ** attempt))  # Exponential backoff
            return model.generate_content(prompt)
        except Exception as e:
            if "ResourceExhausted" in str(e) and attempt < max_retries - 1:
                st.warning(f"API quota exceeded. Retrying in {initial_delay * (2 ** (attempt + 1))} seconds...")
            else:
                raise e
    raise Exception("Max retries reached. Please try again later.")

def extract_text_from_pdf(file):
    pdf_reader = PyPDF2.PdfReader(file)
    text = ""
    for page in pdf_reader.pages:
        text += page.extract_text() + "\n\n"
    return text

def extract_text_from_docx(file):
    doc = docx.Document(file)
    text = ""
    for para in doc.paragraphs:
        text += para.text + "\n\n"
    return text

def split_into_sections(text):
    sections = []
    current_section = ""
    lines = text.split('\n')
    for line in lines:
        if line.strip().isupper() or line.strip().startswith('#'):
            if current_section:
                sections.append(current_section.strip())
            current_section = line + "\n"
        else:
            current_section += line + "\n"
    if current_section:
        sections.append(current_section.strip())
    return sections

def summarize_text(text, model):
    prompt = f"Summarize the following scientific text, reducing the word count while maintaining key information and technical details:\n\n{text}"
    response = generate_with_backoff(model, prompt)
    return response.text

def generate_podcast_script(text, model):
    prompt = f"""
    Transform the following scientific paper into an engaging 5-minute podcast script between two hosts, Alice (a subject expert) and Bob (a curious learner):

    {text}

    Make it conversational, informative, and engaging. Include appropriate technical explanations, analogies, and real-world applications.
    Structure the podcast with an introduction, main discussion points, and a conclusion.
    The podcast should be approximately 5 minutes long when read aloud.
    End the script with the phrase 'END_OF_PODCAST'.
    """
    full_script = ""
    while "END_OF_PODCAST" not in full_script:
        response = generate_with_backoff(model, prompt)
        full_script += response.text + "\n"
        if "END_OF_PODCAST" not in full_script:
            prompt = "Continue the podcast script, maintaining the conversational and informative tone. Remember to end with 'END_OF_PODCAST' when complete."
    
    return full_script.replace("END_OF_PODCAST", "").strip()

def text_to_speech(text):
    try:
        tts = gTTS(text=text, lang='en')
        fp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        tts.save(fp.name)
        return fp.name
    except Exception as e:
        st.error(f"Error in text-to-speech conversion: {str(e)}")
        return None

def create_download_link(file_path, filename):
    with open(file_path, "rb") as file:
        contents = file.read()
    b64 = base64.b64encode(contents).decode()
    return f'<a href="data:audio/mp3;base64,{b64}" download="{filename}">Download {filename}</a>'

def main():
    st.title("Scientific Paper Analyzer")

    api_key = st.text_input("Enter your Gemini API Key:", type="password")
    if not api_key:
        st.warning("Please enter your Gemini API key to proceed.")
        return

    model = initialize_gemini_api(api_key)

    uploaded_file = st.file_uploader("Upload your scientific paper (PDF, DOCX, or TXT)", type=["pdf", "docx", "txt"])

    if uploaded_file is not None:
        file_extension = os.path.splitext(uploaded_file.name)[1].lower()

        if file_extension == ".pdf":
            text = extract_text_from_pdf(uploaded_file)
        elif file_extension in [".docx", ".doc"]:
            text = extract_text_from_docx(uploaded_file)
        elif file_extension == ".txt":
            text = uploaded_file.getvalue().decode("utf-8")
        else:
            st.error("Unsupported file format. Please upload a PDF, DOCX, or TXT file.")
            return

        sections = split_into_sections(text)

        st.subheader("Document Analysis")

        full_summary = ""
        for i, section in enumerate(sections, 1):
            with st.expander(f"Section {i}"):
                st.text(section[:500] + "..." if len(section) > 500 else section)
                summary = summarize_text(section, model)
                st.markdown("**Summary:**")
                st.write(summary)
                full_summary += summary + "\n\n"

        st.subheader("Full Document Summary")
        st.write(full_summary)

        st.download_button(
            label="Download Full Summary",
            data=full_summary,
            file_name="paper_summary.txt",
            mime="text/plain"
        )

        # Audio Summary
        if st.button("Generate Audio Summary"):
            with st.spinner("Generating audio summary..."):
                try:
                    audio_file = text_to_speech(full_summary)
                    if audio_file:
                        st.audio(audio_file)
                        st.markdown(create_download_link(audio_file, "summary_audio.mp3"), unsafe_allow_html=True)
                    else:
                        st.error("Failed to generate audio summary. Please try again.")
                except Exception as e:
                    st.error(f"Error generating audio summary: {str(e)}")

        # Podcast Generation
        if 'podcast_script' not in st.session_state:
            st.session_state.podcast_script = None

        if st.button("Generate Podcast Script"):
            with st.spinner("Generating podcast script..."):
                try:
                    st.session_state.podcast_script = generate_podcast_script(text, model)
                    st.text_area("Podcast Script", st.session_state.podcast_script, height=300)
                    
                    st.download_button(
                        label="Download Podcast Script",
                        data=st.session_state.podcast_script,
                        file_name="podcast_script.txt",
                        mime="text/plain"
                    )
                except Exception as e:
                    st.error(f"Error generating podcast script: {str(e)}")

        if st.session_state.podcast_script and st.button("Generate Podcast Audio"):
            with st.spinner("Generating podcast audio..."):
                try:
                    podcast_audio = text_to_speech(st.session_state.podcast_script)
                    if podcast_audio:
                        st.subheader("Podcast Audio")
                        st.audio(podcast_audio)
                        st.markdown(create_download_link(podcast_audio, "podcast_audio.mp3"), unsafe_allow_html=True)
                    else:
                        st.error("Failed to generate podcast audio. Please try again.")
                except Exception as e:
                    st.error(f"Error generating podcast audio: {str(e)}")

if __name__ == "__main__":
    main()