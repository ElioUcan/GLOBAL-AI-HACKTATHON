CREATE TABLE IF NOT EXISTS jerga (
    id SERIAL PRIMARY KEY,
    term TEXT NOT NULL,
    meaning TEXT NOT NULL,
    harm_category TEXT NOT NULL,
    region TEXT DEFAULT 'Yucatan'
);

CREATE TABLE IF NOT EXISTS results (
    id SERIAL PRIMARY KEY,
    jerga_id INTEGER REFERENCES jerga(id),
    attack_technique TEXT,
    generated_prompt TEXT,
    target_model TEXT,
    target_provider TEXT,
    response TEXT,
    jailbreak_success BOOLEAN,
    confidence NUMERIC,
    severity TEXT,
    judge_reasoning TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
