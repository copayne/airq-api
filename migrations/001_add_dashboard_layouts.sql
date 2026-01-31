-- Migration: Add dashboard_layouts table
-- Run this script on existing databases to add the dashboard layouts feature
-- For new databases, init_db.py will create this table automatically

CREATE TABLE IF NOT EXISTS dashboard_layouts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    layout_data JSONB NOT NULL,
    is_last_used BOOLEAN DEFAULT FALSE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    CONSTRAINT unique_layout_name_per_user UNIQUE (user_id, name)
);

-- Create indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_dashboard_layouts_user_id ON dashboard_layouts(user_id);
CREATE INDEX IF NOT EXISTS idx_dashboard_layouts_user_last_used ON dashboard_layouts(user_id, is_last_used);

-- Add a comment for documentation
COMMENT ON TABLE dashboard_layouts IS 'Stores user dashboard layout configurations including widget positions and criteria';
