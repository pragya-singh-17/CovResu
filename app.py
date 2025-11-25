import streamlit as st
import requests
import json
import os
import re  # Added regex for better JSON parsing
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from datetime import datetime
import io

OLLAMA_MODEL = "gemma2:9b" 
OLLAMA_API_URL = "http://localhost:11434/api/generate"

def query_ollama(prompt):
    """
    Sends a prompt to the local Ollama and returns the text response.
    """
    try:
        payload = {
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.7 
            }
        }
        response = requests.post(OLLAMA_API_URL, json=payload)
        response.raise_for_status()
        return response.json().get("response", "")
    except requests.exceptions.ConnectionError:
        return "Error: Could not connect to Ollama. Make sure Ollama is running."
    except Exception as e:
        return f"Error: {str(e)}"

# AI GENERATION FUNCTIONS

def generate_cover_letter(user_data, job_description):
    prompt = f"""
    You are a professional resume writer. Write a cover letter.
    
    Candidate Name: {user_data['name']}
    Current Role: {user_data.get('current_role', 'Not specified')}
    Skills: {', '.join(user_data.get('skills', []))}
    
    Target Job Description:
    {job_description}
    
    Instructions:
    1. Tone: Professional, confident, and enthusiastic.
    2. Structure: Introduction (why I'm applying), Body (matching my skills to the JD), Conclusion (call to action).
    3. Do NOT include placeholders like [Insert Date]. Use today's date.
    4. Keep it under 500 words.
    """
    return query_ollama(prompt)

def tailor_resume_experience(experience_list, job_description):
    """
    Uses Local LLM to rewrite experience bullet points.
    """
    experience_str = json.dumps(experience_list)
    
    prompt = f"""
    Act as an Expert Resume Writer.
    Task: Rewrite the 'description' field of the work experience JSON below to match the Job Description.
    
    Job Description Keywords:
    {job_description}
    
    Original Experience JSON:
    {experience_str}
    
    RULES:
    1. Output ONLY valid JSON.
    2. Return a LIST of dictionaries.
    3. Keep the exact same keys (title, company, duration), only change 'description'.
    4. Do not add conversational filler like "Here is the JSON".
    5. Ensure all quotes are escaped correctly.
    """
    
    response_text = query_ollama(prompt)
    
    # IMPROVED JSON EXTRACTION
    try:
        
        match = re.search(r'\[.*\]', response_text, re.DOTALL)
        
        if match:
            json_str = match.group(0)
            return json.loads(json_str)
        else:
            clean_text = response_text.replace('```json', '').replace('```', '').strip()
            return json.loads(clean_text)
            
    except json.JSONDecodeError as e:
        st.error(f"AI Error: The model returned invalid JSON. (Error: {str(e)})")
        st.warning("Raw Model Output (for debugging):")
        st.code(response_text)
        return experience_list

# PDF GENERATION FUNCTIONS

def create_resume_pdf(user_data, use_tailored=False):
    try:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
        styles = getSampleStyleSheet()
        story = []

        # Styles
        name_style = ParagraphStyle('Name', parent=styles['Heading1'], fontSize=22, spaceAfter=5, alignment=TA_CENTER)
        contact_style = ParagraphStyle('Contact', parent=styles['Normal'], fontSize=10, alignment=TA_CENTER, textColor=colors.darkgrey)
        section_header = ParagraphStyle('Section', parent=styles['Heading2'], fontSize=12, spaceBefore=15, spaceAfter=6, textTransform='uppercase')
        role_style = ParagraphStyle('Role', parent=styles['Heading3'], fontSize=11, spaceBefore=8, spaceAfter=2)
        company_style = ParagraphStyle('Company', parent=styles['Normal'], fontSize=11, textColor=colors.black, spaceAfter=2)
        desc_style = ParagraphStyle('Desc', parent=styles['Normal'], fontSize=10, leading=14)
        
        # Header
        story.append(Paragraph(user_data.get('name', 'Name'), name_style))
        contact_info = f"{user_data.get('email', '')} | {user_data.get('phone', '')} | {user_data.get('current_role', '')}"
        story.append(Paragraph(contact_info, contact_style))
        story.append(Spacer(1, 20))

        # Summary
        if user_data.get('summary'):
            story.append(Paragraph('Professional Summary', section_header))
            story.append(Paragraph(user_data['summary'], desc_style))
            story.append(Spacer(1, 10))

        # Education
        if user_data.get('education'):
            story.append(Paragraph('Education', section_header))
            for edu in user_data['education']:
                edu_text = f"<b>{edu.get('degree', '')}</b> - {edu.get('institution', '')} ({edu.get('year', '')})"
                story.append(Paragraph(edu_text, desc_style))

        # Experience
        experience_source = user_data.get('tailored_experience') if use_tailored and user_data.get('tailored_experience') else user_data.get('experience', [])
        
        if experience_source:
            story.append(Paragraph('Experience', section_header))
            for exp in experience_source:
                story.append(Paragraph(f"<b>{exp.get('title', '')}</b>", role_style))
                comp_dur = f"{exp.get('company', '')} | <i>{exp.get('duration', '')}</i>"
                story.append(Paragraph(comp_dur, company_style))
                story.append(Paragraph(exp.get('description', ''), desc_style))
                story.append(Spacer(1, 10))

        # Skills
        if user_data.get('skills'):
            story.append(Paragraph('Technical Skills', section_header))
            story.append(Paragraph(", ".join(user_data['skills']), desc_style))
            story.append(Spacer(1, 10))


        # Projects
        if user_data.get('projects'):
            story.append(Paragraph('Projects', section_header))
            for proj in user_data['projects']:
                story.append(Paragraph(f"<b>{proj.get('title', '')}</b>", role_style))
                if proj.get('tech'):
                    story.append(Paragraph(f"<i>Tech: {proj['tech']}</i>", desc_style))
                story.append(Paragraph(proj.get('description', ''), desc_style))
                story.append(Spacer(1, 8))

        
        doc.build(story)
        buffer.seek(0)
        return buffer
    except Exception as e:
        st.error(f"PDF Error: {e}")
        return None

def create_cover_letter_pdf(text, user_data):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50)
    styles = getSampleStyleSheet()
    story = []
    
    normal_style = ParagraphStyle('Normal', parent=styles['Normal'], fontSize=11, leading=16)
    
    story.append(Paragraph(user_data.get('name', ''), styles['Heading2']))
    story.append(Paragraph(user_data.get('email', ''), normal_style))
    story.append(Paragraph(user_data.get('phone', ''), normal_style))
    story.append(Spacer(1, 20))
    
    story.append(Paragraph(datetime.now().strftime("%B %d, %Y"), normal_style))
    story.append(Spacer(1, 20))
    
    for para in text.split('\n\n'):
        story.append(Paragraph(para, normal_style))
        story.append(Spacer(1, 10))
        
    doc.build(story)
    buffer.seek(0)
    return buffer

# MAIN

def main():
    st.set_page_config(page_title="Local AI Resume Builder", page_icon="🦙", layout="wide")
    
    st.sidebar.title("🦙 Local AI Resume")
    st.sidebar.markdown(f"Running Model: **{OLLAMA_MODEL}**")
    
    # Initialize Session State
    if 'current_step' not in st.session_state:
        st.session_state.current_step = 1
        
    if 'user_data' not in st.session_state:
        st.session_state.user_data = {
            'name': '', 'email': '', 'phone': '', 'current_role': '', 'summary': '',
            'skills': [], 'experience': [], 'projects': [], 'education': [],
            'job_description': '', 'tailored_experience': []
        }

    # Step 1: Personal Info
    if st.session_state.current_step == 1:
        st.header("👤 Personal Information")
        c1, c2 = st.columns(2)
        with c1:
            st.session_state.user_data['name'] = st.text_input("Name", st.session_state.user_data['name'])
            st.session_state.user_data['email'] = st.text_input("Email", st.session_state.user_data['email'])
        with c2:
            st.session_state.user_data['phone'] = st.text_input("Phone", st.session_state.user_data['phone'])
            st.session_state.user_data['current_role'] = st.text_input("Current Role", st.session_state.user_data['current_role'])
        
        st.session_state.user_data['summary'] = st.text_area("Professional Summary", st.session_state.user_data['summary'])
        
        if st.button("Next: Skills & Experience ➡"): 
            st.session_state.current_step = 2
            st.rerun()
            
    # Step 2: Skills & Experience
    elif st.session_state.current_step == 2:
        st.header("🛠 Skills & Experience")
        
        skills_txt = st.text_area("Skills (comma sep)", ", ".join(st.session_state.user_data['skills']))
        st.session_state.user_data['skills'] = [s.strip() for s in skills_txt.split(',') if s.strip()]
        
        st.subheader("Work Experience")
        for i, exp in enumerate(st.session_state.user_data['experience']):
            with st.expander(f"Job {i+1}", expanded=True):
                c1, c2 = st.columns(2)
                exp['title'] = c1.text_input(f"Title {i}", exp['title'])
                exp['company'] = c2.text_input(f"Company {i}", exp['company'])
                exp['duration'] = c1.text_input(f"Duration {i}", exp['duration'])
                exp['description'] = st.text_area(f"Description {i}", exp['description'])
        
        if st.button("➕ Add Job"): 
            st.session_state.user_data['experience'].append({'title':'', 'company':'', 'duration':'', 'description':''})
            st.rerun()
        
        c1, c2 = st.columns([1, 1])
        if c1.button("⬅ Back"): 
            st.session_state.current_step = 1
            st.rerun()
        if c2.button("Next: Projects & Education ➡"): 
            st.session_state.current_step = 3
            st.rerun()

    # Step 3: Projects & Education
    elif st.session_state.current_step == 3:
        st.header("🚀 Projects & Education")
        
        st.subheader("Projects")
        for i, proj in enumerate(st.session_state.user_data['projects']):
            with st.expander(f"Project {i+1}", expanded=True):
                proj['title'] = st.text_input(f"Project Name {i}", proj['title'])
                proj['tech'] = st.text_input(f"Tech Stack {i}", proj['tech'])
                proj['description'] = st.text_area(f"Project Desc {i}", proj['description'])
        
        if st.button("➕ Add Project"):
            st.session_state.user_data['projects'].append({'title': '', 'tech': '', 'description': ''})
            st.rerun()

        st.divider()
        
        st.subheader("Education")
        for i, edu in enumerate(st.session_state.user_data['education']):
            with st.expander(f"Education {i+1}", expanded=True):
                edu['degree'] = st.text_input(f"Degree {i}", edu['degree'])
                edu['institution'] = st.text_input(f"Institution {i}", edu['institution'])
                edu['year'] = st.text_input(f"Year {i}", edu['year'])

        if st.button("➕ Add Education"):
            st.session_state.user_data['education'].append({'degree': '', 'institution': '', 'year': ''})
            st.rerun()

        c1, c2 = st.columns([1, 1])
        if c1.button("⬅ Back"): 
            st.session_state.current_step = 2
            st.rerun()
        if c2.button("Next: Target Job ➡"): 
            st.session_state.current_step = 4
            st.rerun()

    # Step 4: Job Description
    elif st.session_state.current_step == 4:
        st.header("🎯 Target Job Description")
        st.info("Paste the Job Description (JD) below.")
        st.session_state.user_data['job_description'] = st.text_area("Paste JD Here", st.session_state.user_data['job_description'], height=300)
        
        c1, c2 = st.columns([1, 1])
        if c1.button("⬅ Back"): 
            st.session_state.current_step = 3
            st.rerun()
        if c2.button("Finalize & Generate ➡", type="primary"): 
            st.session_state.current_step = 5
            st.rerun()

    # Step 5: Generate
    elif st.session_state.current_step == 5:
        st.header("✨ Generate Documents")
        
        tab1, tab2 = st.tabs(["📄 Resume", "✉️ Cover Letter"])
        
        with tab1:
            st.subheader("Resume Tailoring")
            if st.button("✨ Auto-Tailor Experience with AI"):
                with st.spinner(f"Rewriting bullets with {OLLAMA_MODEL}..."):
                    tailored = tailor_resume_experience(st.session_state.user_data['experience'], st.session_state.user_data['job_description'])
                    st.session_state.user_data['tailored_experience'] = tailored
                    if st.session_state.user_data.get('tailored_experience'):
                         st.success("Tailoring complete!")
            
            # Comparison View
            if st.session_state.user_data.get('tailored_experience'):
                use_tailored = st.checkbox("Use AI-Tailored Content in PDF", value=True)
                for i, orig in enumerate(st.session_state.user_data['experience']):
                    if i < len(st.session_state.user_data['tailored_experience']):
                        new = st.session_state.user_data['tailored_experience'][i]
                        with st.expander(f"Compare: {orig['title']}"):
                            c1, c2 = st.columns(2)
                            c1.caption("Original")
                            c1.write(orig['description'])
                            c2.caption("AI Version")
                            c2.write(new['description'])
            else:
                use_tailored = False
            
            if st.button("📥 Download Resume PDF"):
                pdf = create_resume_pdf(st.session_state.user_data, use_tailored)
                if pdf:
                    st.download_button("Download Resume", pdf, "resume.pdf", "application/pdf")

        with tab2:
            st.subheader("Cover Letter")
            if st.button("📝 Write Cover Letter"):
                with st.spinner("Writing..."):
                    cl = generate_cover_letter(st.session_state.user_data, st.session_state.user_data['job_description'])
                    st.session_state.cl = cl
            
            if 'cl' in st.session_state:
                st.text_area("Result", st.session_state.cl, height=400)
                cl_pdf = create_cover_letter_pdf(st.session_state.cl, st.session_state.user_data)
                st.download_button("📥 Download Cover Letter PDF", cl_pdf, "cover_letter.pdf", "application/pdf")
        
        if st.button("🔄 Start Over"):
            st.session_state.clear()
            st.rerun()

if __name__ == '__main__':
    main()