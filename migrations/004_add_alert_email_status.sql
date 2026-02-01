-- Migration: Add email delivery status tracking to alert history
-- Version: 004
-- Description: Adds email_status column to alert_history for tracking
--              whether the alert email was sent successfully.

ALTER TABLE alert_history
    ADD COLUMN IF NOT EXISTS email_status VARCHAR(20) NOT NULL DEFAULT 'skipped';

COMMENT ON COLUMN alert_history.email_status IS 'Email delivery status: sent, failed, or skipped';
