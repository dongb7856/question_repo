-- question_repo: 成人高考专升本真题库

CREATE TABLE IF NOT EXISTS subjects (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(50) UNIQUE NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS exam_papers (
    id          SERIAL PRIMARY KEY,
    subject_id  INT NOT NULL REFERENCES subjects(id),
    year        INT NOT NULL,
    title       TEXT,
    source_url  TEXT,
    source_file TEXT NOT NULL,
    source_kind VARCHAR(20) NOT NULL DEFAULT 'txt',
    notes       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (subject_id, year, source_file)
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'question_type') THEN
        CREATE TYPE question_type AS ENUM (
            'choice',
            'short_answer',
            'essay',
            'case_analysis',
            'other'
        );
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS questions (
    id              SERIAL PRIMARY KEY,
    exam_paper_id   INT NOT NULL REFERENCES exam_papers(id) ON DELETE CASCADE,
    number          INT NOT NULL,
    question_type   question_type NOT NULL DEFAULT 'other',
    section_title   TEXT,
    stem            TEXT NOT NULL,
    options         JSONB,
    answer          TEXT,
    explanation     TEXT,
    raw_text        TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (exam_paper_id, number)
);

CREATE INDEX IF NOT EXISTS idx_questions_exam_paper ON questions (exam_paper_id);
CREATE INDEX IF NOT EXISTS idx_questions_type ON questions (question_type);
CREATE INDEX IF NOT EXISTS idx_questions_stem_fts ON questions
    USING gin (to_tsvector('simple', coalesce(stem, '')));
CREATE INDEX IF NOT EXISTS idx_questions_options ON questions USING gin (options);

CREATE OR REPLACE VIEW v_questions AS
SELECT
    q.id,
    s.name AS subject,
    p.year,
    p.title AS paper_title,
    q.number,
    q.question_type,
    q.section_title,
    q.stem,
    q.options,
    q.answer,
    p.source_file
FROM questions q
JOIN exam_papers p ON p.id = q.exam_paper_id
JOIN subjects s ON s.id = p.subject_id;
