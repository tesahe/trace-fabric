-- Add up migration script here



CREATE TYPE lead_status AS ENUM ('PENDING', 'ACCEPTED', 'REJECTED');

CREATE TABLE leads (

    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    url TEXT NOT NULL UNIQUE,

    status lead_status NOT NULL DEFAULT 'PENDING',

    raw_payload JSONB NOT NULL,

    rejection_reason TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()

);