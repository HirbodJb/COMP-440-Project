-- COMP 440 Course Project - Phase 1
-- Database schema
-- Run this once to create the database and table:
--   mysql -u root -p < schema.sql

CREATE DATABASE IF NOT EXISTS comp440_p1;
USE comp440_p1;

DROP TABLE IF EXISTS user;

CREATE TABLE user (
    username   VARCHAR(50)  NOT NULL,
    password   VARCHAR(255) NOT NULL,   -- stores a salted hash, never plaintext
    firstName  VARCHAR(50)  NOT NULL,
    lastName   VARCHAR(50)  NOT NULL,
    email      VARCHAR(100) NOT NULL,
    phone      VARCHAR(20)  NOT NULL,
    PRIMARY KEY (username),
    UNIQUE KEY uq_email (email),
    UNIQUE KEY uq_phone (phone)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
