# Architecture Update — Milestone 2.6

## 1. Overview

Milestone 2.6 extends the CAREER ARENA interview platform with two
independent AI evaluation systems:

1. Resume suitability evaluation.
2. Interview performance evaluation.

Both evaluations are generated after the candidate completes the
three main technical interview questions.

The system stores the two reports independently and associates them
with the candidate, interview session, selected resume and selected
job role.

The existing Milestone 2.5 interview orchestration and LiveKit voice
pipeline remain responsible for conducting the interview.

Milestone 2.6 adds evaluation and reporting functionality without
changing the core interview-question selection workflow.

---

## 2. High-Level Architecture

```text
                         FRONTEND
                            |
                            |
                   React / TypeScript
                            |
              +-------------+-------------+
              |                           |
       Interview Workflow          Evaluation Dashboard
              |                           |
              |                           |
              +-------------+-------------+
                            |
                       FastAPI
                            |
              +-------------+-------------+
              |                           |
       Interview API              Evaluation Report API
              |                           |
              |                           |
     Session Management         Evaluation Report Service
              |                           |
              |               +-----------+-----------+
              |               |                       |
              |        Resume Evaluation      Interview Evaluation
              |               |                       |
              |               |                       |
              |          Resume Data            Transcript Data
              |               |                       |
              |               +-----------+-----------+
              |                           |
              |                      LLM Provider
              |                           |
              +---------------------------+
                            |
                     Database Layer
                            |
             +--------------+--------------+
             |                             |
       interview_data.db           role_question_bank.db
             |                             |
      Candidate Records              Role Information
      Resume Records                 Role Technologies
      Interview Sessions             Question Bank
      Transcript Messages
      Evaluation Reports