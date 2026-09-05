"""Prompt templates for AI operations."""

RESUME_MATCH_PROMPT = """You are an expert technical recruiter evaluating a candidate for a job.

JOB DESCRIPTION:
{job_description}

CANDIDATE RESUME:
{resume_text}

CANDIDATE SKILLS:
- {skills}

Score how well this candidate matches the job requirements on a scale of 0.0 to 1.0.
Consider: required skills, experience level, domain knowledge, and overall fit.

Return JSON with:
- score: float between 0.0 and 1.0
- reasoning: brief explanation of the score
- matched_skills: list of skills from the job that the candidate has
- missing_skills: list of important skills from the job that the candidate lacks"""

QA_GENERATION_PROMPT = """You are helping a job applicant answer application questions.

JOB DESCRIPTION:
{job_description}

CANDIDATE RESUME:
{resume_text}

QUESTIONS TO ANSWER:
{questions}

Generate concise, professional answers tailored to this specific job and the candidate's experience.
Each answer should be 2-4 sentences, highlighting relevant experience from the resume.

Return JSON with:
- answers: object mapping each question to its answer"""

COVER_LETTER_PROMPT = """Write a compelling cover letter for this job application.

JOB TITLE: {job_title}
COMPANY: {company}

JOB DESCRIPTION:
{job_description}

CANDIDATE RESUME:
{resume_text}

Write a professional cover letter (3-4 paragraphs) that:
1. Opens with enthusiasm for the specific role and company
2. Highlights 2-3 most relevant achievements from the resume
3. Connects candidate's experience to the job requirements
4. Closes with a call to action

Keep it under 250 words. Be specific, not generic.
Use ONLY facts present in the resume. Do not invent employers, projects, degrees, certifications, metrics, or technologies."""

APPLY_DECISION_PROMPT = """You are an AI career advisor deciding whether a candidate should apply to a job.

JOB TITLE: {job_title}
COMPANY: {company}

JOB DESCRIPTION:
{job_description}

CANDIDATE RESUME:
{resume_text}

RESUME MATCH SCORE: {match_score}/1.0

Consider:
- Match score (below 0.5 = likely not qualified)
- Required years of experience vs candidate's experience
- Must-have skills vs candidate's skills
- Location/remote preferences
- Company culture fit indicators

Return JSON with:
- should_apply: boolean
- reasoning: brief explanation of the decision"""