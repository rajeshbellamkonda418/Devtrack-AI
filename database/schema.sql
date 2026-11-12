-- Legacy MySQL source schema only. The application backend now uses MongoDB.
-- See MONGODB_MIGRATION.md to migrate records from an existing MySQL database.
CREATE DATABASE IF NOT EXISTS devtrack_ai;
USE devtrack_ai;
CREATE TABLE IF NOT EXISTS users (

    id INT AUTO_INCREMENT PRIMARY KEY,

    name VARCHAR(80) NOT NULL UNIQUE,

    password_hash VARCHAR(255) NOT NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

);

CREATE TABLE IF NOT EXISTS applications (

    id INT AUTO_INCREMENT PRIMARY KEY,

    user_id INT NULL,

    company VARCHAR(120) NOT NULL,

    role VARCHAR(120) NOT NULL,

    status ENUM(
        'Applied',
        'Interview',
        'Selected',
        'Rejected'
    ) NOT NULL DEFAULT 'Applied',

    skills TEXT,

    applied_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX applications_user_id_idx (user_id)
);