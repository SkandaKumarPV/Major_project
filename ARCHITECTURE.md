# CAREER ARENA — System Architecture

**Project:** CAREER ARENA: Gamified AI-Based Recruitment and Interview Simulation

**Architecture:** React + FastAPI + LiveKit Agents + SQLite

**Scope:** Phase 1 and Phase 2, Milestones 2.0–2.7

---

# 1. Architecture Overview

CAREER ARENA is a single-candidate AI interview simulation platform.

The application combines a React frontend, a FastAPI backend,
a LiveKit Agents worker, speech-processing services, a configurable
LLM provider, and two separate SQLite databases.

The backend owns candidate records, resume processing, interview
progress, technical question selection, transcript persistence
and evaluation reports.

The LLM interprets candidate responses and generates contextual
interviewer responses. It does not own the authoritative interview
state or override backend-enforced question limits.

## 1.1 High-level architecture

```text
                       CANDIDATE
                           |
                           v
                 REACT / TYPESCRIPT
                           |
                  FastAPI HTTP API
                           |
           +---------------+----------------+
           |               |                |
           v               v                v
       Guest API       Resume API      Interview API
           |               |                |
           v               v                v
     Guest Identity   Resume Services   Session Services
                           |                |
                           |                v
                           |         Interview Runtime
                           |                |
                           |       +--------+---------+
                           |       |                  |
                           |       v                  v
                           |   Resume Discussion   Technical
                           |       Service        Interview
                           |                          Service
                           |                           |
                           |                           v
                           |                    Question Bank
                           |                    Repository
                           |
                           v
                   Private File Storage


                  LIVEKIT VOICE WORKER
                           |
                           v
                      LiveKit Room
                           |
              +------------+-------------+
              |            |             |
              v            v             v
          Deepgram       LLM          Cartesia
            STT         Provider         TTS
              |            |             |
              +------------+-------------+
                           |
                           v
                LiveKit Session Controller
                           |
                           v
                 Interview Runtime Service
                           |
                           v
                Persistent Interview State
                           |
             +-------------+--------------+
             |                            |
             v                            v
       Transcript Recorder          Evaluation Service
                                          |
                              +-----------+-----------+
                              |                       |
                              v                       v
                      Resume Evaluation       Interview Evaluation
                              |                       |
                              +-----------+-----------+
                                          |
                                          v
                                  Evaluation Report
                                          |
                                          v
                                  Candidate Dashboard