-- COMP 440 Phase 2 migration
-- Existing Phase 1 teammates should run this entire file once in MySQL
-- Workbench. It preserves the existing user table and registered accounts.
--
-- This file is intentionally additive: it extends the Phase 1 database instead
-- of dropping and rebuilding it. CREATE TABLE IF NOT EXISTS and INSERT IGNORE
-- also make an accidental second run safe. Keep schema.sql in sync whenever a
-- Phase 2 table, constraint, index, or trigger changes here.

-- Select the same local database created during Phase 1. Teammates using a
-- custom COMP440_DB_NAME must update this line to match their local setting.
USE comp440_p1;

-- Phase 1 installations may use MySQL 8's server-default collation while the
-- Phase 2 tables use an explicit portable collation. Foreign-key text columns
-- must match exactly, so normalize the existing user table without changing
-- its rows.
ALTER TABLE user CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- Marketplace listings
-- ---------------------------------------------------------------------------
-- Each item belongs to one registered seller. Status keeps sold and taken-down
-- listings available for seller/purchase history while the application only
-- shows active listings in the public feed.
CREATE TABLE IF NOT EXISTS item (
    itemId INT NOT NULL AUTO_INCREMENT,
    title VARCHAR(120) NOT NULL,
    description TEXT NOT NULL,
    datePosted DATE NOT NULL,
    price DECIMAL(10,2) NOT NULL,
    seller VARCHAR(50) NOT NULL,
    status ENUM('active', 'sold', 'removed') NOT NULL DEFAULT 'active',
    -- The seller/date index supports the daily posting rule and seller history.
    PRIMARY KEY (itemId),
    KEY idx_item_seller_date (seller, datePosted),
    KEY idx_item_date (datePosted),
    CONSTRAINT fk_item_seller FOREIGN KEY (seller) REFERENCES user(username),
    CONSTRAINT chk_item_price CHECK (price >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Safe on both new and previously migrated databases. MODIFY is needed because
-- CREATE TABLE IF NOT EXISTS does not add 'removed' to an older status enum.
ALTER TABLE item
    MODIFY COLUMN status ENUM('active', 'sold', 'removed') NOT NULL DEFAULT 'active';

-- ---------------------------------------------------------------------------
-- Categories and item/category relationships
-- ---------------------------------------------------------------------------
-- Categories are shared dictionary values rather than repeated free-form text.
-- The CHECK constraint mirrors the assignment's lowercase single-word rule.
CREATE TABLE IF NOT EXISTS category (
    categoryName VARCHAR(50) NOT NULL,
    PRIMARY KEY (categoryName),
    CONSTRAINT chk_category_lowercase_word CHECK (categoryName REGEXP '^[a-z]+$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Item post history is an audit table, not a second copy of each listing. Rows
-- remain even after an unsold listing is deleted, preventing a seller from
-- deleting two posts and bypassing the two-items-per-day limit.
CREATE TABLE IF NOT EXISTS item_post_history (
    itemId INT NOT NULL,
    seller VARCHAR(50) NOT NULL,
    datePosted DATE NOT NULL,
    PRIMARY KEY (itemId),
    KEY idx_post_history_user_date (seller, datePosted),
    CONSTRAINT fk_post_history_user FOREIGN KEY (seller) REFERENCES user(username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Composite primary key enforces one relationship per item/category pair.
-- ON DELETE CASCADE removes relationship rows when either side is removed; it
-- never deletes the remaining item or category itself.
CREATE TABLE IF NOT EXISTS item_category (
    itemId INT NOT NULL,
    categoryName VARCHAR(50) NOT NULL,
    PRIMARY KEY (itemId, categoryName),
    KEY idx_item_category_name (categoryName, itemId),
    CONSTRAINT fk_item_category_item FOREIGN KEY (itemId) REFERENCES item(itemId) ON DELETE CASCADE,
    CONSTRAINT fk_item_category_category FOREIGN KEY (categoryName) REFERENCES category(categoryName) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- Reviews and community interactions
-- ---------------------------------------------------------------------------
-- Rating uses the four exact values required by the assignment. The unique
-- reviewer/item key is the database-level one-review-per-item rule.
CREATE TABLE IF NOT EXISTS review (
    reviewId INT NOT NULL AUTO_INCREMENT,
    itemId INT NOT NULL,
    reviewer VARCHAR(50) NOT NULL,
    rating ENUM('Poor', 'Fair', 'Good', 'Excellent') NOT NULL,
    comment VARCHAR(500) NOT NULL,
    reviewDate DATE NOT NULL,
    PRIMARY KEY (reviewId),
    UNIQUE KEY uq_review_reviewer_item (reviewer, itemId),
    KEY idx_review_item (itemId),
    KEY idx_review_reviewer_date (reviewer, reviewDate),
    CONSTRAINT fk_review_item FOREIGN KEY (itemId) REFERENCES item(itemId) ON DELETE CASCADE,
    CONSTRAINT fk_review_reviewer FOREIGN KEY (reviewer) REFERENCES user(username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- The composite primary key makes repeated likes impossible while allowing the
-- same user to like many different items. Likes disappear with their item.
CREATE TABLE IF NOT EXISTS item_like (
    itemId INT NOT NULL,
    username VARCHAR(50) NOT NULL,
    likedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (itemId, username),
    CONSTRAINT fk_like_item FOREIGN KEY (itemId) REFERENCES item(itemId) ON DELETE CASCADE,
    CONSTRAINT fk_like_user FOREIGN KEY (username) REFERENCES user(username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Keep a permanent count of review submissions even if deleting an item causes
-- its review rows to be removed through the foreign-key cascade. Without this
-- audit table, deletion could reset a reviewer's three-per-day count.
CREATE TABLE IF NOT EXISTS review_submission_history (
    reviewId INT NOT NULL,
    reviewer VARCHAR(50) NOT NULL,
    reviewDate DATE NOT NULL,
    PRIMARY KEY (reviewId),
    KEY idx_review_history_user_date (reviewer, reviewDate),
    CONSTRAINT fk_review_history_user FOREIGN KEY (reviewer) REFERENCES user(username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- Purchases
-- ---------------------------------------------------------------------------
-- A listing represents one sellable item, so the unique itemId key permits only
-- one purchase. pricePaid preserves the checkout price if a listing changes or
-- is later taken down. Purchase rows intentionally do not cascade on deletion.
CREATE TABLE IF NOT EXISTS purchase (
    purchaseId INT NOT NULL AUTO_INCREMENT,
    itemId INT NOT NULL,
    buyer VARCHAR(50) NOT NULL,
    seller VARCHAR(50) NOT NULL,
    pricePaid DECIMAL(10,2) NOT NULL,
    purchaseDate DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (purchaseId),
    UNIQUE KEY uq_purchase_item (itemId),
    KEY idx_purchase_buyer (buyer),
    CONSTRAINT fk_purchase_item FOREIGN KEY (itemId) REFERENCES item(itemId),
    CONSTRAINT fk_purchase_buyer FOREIGN KEY (buyer) REFERENCES user(username),
    CONSTRAINT fk_purchase_seller FOREIGN KEY (seller) REFERENCES user(username),
    CONSTRAINT chk_purchase_distinct_users CHECK (buyer <> seller),
    CONSTRAINT chk_purchase_price CHECK (pricePaid >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- Trigger refresh and audit backfill
-- ---------------------------------------------------------------------------
-- MySQL has no CREATE OR REPLACE TRIGGER. Drop only these project-owned trigger
-- names, then recreate their current definitions below. This is what keeps the
-- migration repeatable after a teammate pulls trigger changes.
DROP TRIGGER IF EXISTS trg_item_daily_limit;
DROP TRIGGER IF EXISTS trg_item_post_history;
DROP TRIGGER IF EXISTS trg_review_rules;
DROP TRIGGER IF EXISTS trg_review_submission_history;
DROP TRIGGER IF EXISTS trg_review_no_update;
DROP TRIGGER IF EXISTS trg_review_no_delete;
DROP TRIGGER IF EXISTS trg_purchase_rules;

-- If an earlier Phase 2 version already contains items or reviews, copy their
-- identifiers into the new audit tables before enabling the counting triggers.
-- INSERT IGNORE prevents duplicate audit rows on subsequent migration runs.
INSERT IGNORE INTO item_post_history (itemId, seller, datePosted)
SELECT itemId, seller, datePosted FROM item;

INSERT IGNORE INTO review_submission_history (reviewId, reviewer, reviewDate)
SELECT reviewId, reviewer, reviewDate FROM review;

-- Trigger bodies contain semicolons, so Workbench needs a temporary delimiter
-- until every BEGIN/END block has been created.
DELIMITER $$

-- Normalize the posting date to MySQL's calendar date and reject a third post.
-- Counting the audit table means deleting a listing cannot restore the quota.
CREATE TRIGGER trg_item_daily_limit BEFORE INSERT ON item FOR EACH ROW
BEGIN
    SET NEW.datePosted = CURRENT_DATE();
    IF (SELECT COUNT(*) FROM item_post_history WHERE seller = NEW.seller AND datePosted = NEW.datePosted) >= 2 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'A user may post at most two items per calendar day.';
    END IF;
END$$

-- Record every successful item insert in the same transaction as the item.
-- If the item insert rolls back, this audit insert rolls back with it.
CREATE TRIGGER trg_item_post_history AFTER INSERT ON item FOR EACH ROW
BEGIN
    INSERT INTO item_post_history (itemId, seller, datePosted)
    VALUES (NEW.itemId, NEW.seller, NEW.datePosted);
END$$

-- The BEFORE INSERT review trigger owns the two rules that need data from other
-- tables: sellers cannot review themselves, and users get three reviews daily.
-- The unique constraint on review separately handles one review per item.
CREATE TRIGGER trg_review_rules BEFORE INSERT ON review FOR EACH ROW
BEGIN
    SET NEW.reviewDate = CURRENT_DATE();
    IF EXISTS (SELECT 1 FROM item WHERE itemId = NEW.itemId AND seller = NEW.reviewer) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'A user cannot review their own item.';
    END IF;
    IF (SELECT COUNT(*) FROM review_submission_history WHERE reviewer = NEW.reviewer AND reviewDate = NEW.reviewDate) >= 3 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'A user may submit at most three reviews per calendar day.';
    END IF;
END$$

-- Record the submission only after MySQL accepts the review and all BEFORE
-- trigger/constraint checks have passed.
CREATE TRIGGER trg_review_submission_history AFTER INSERT ON review FOR EACH ROW
BEGIN
    INSERT INTO review_submission_history (reviewId, reviewer, reviewDate)
    VALUES (NEW.reviewId, NEW.reviewer, NEW.reviewDate);
END$$

-- Reviews are permanent assignment records. Blocking UPDATE and DELETE at the
-- database level keeps this rule true even outside the Flask interface.
CREATE TRIGGER trg_review_no_update BEFORE UPDATE ON review FOR EACH ROW
BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Reviews cannot be modified after submission.';
END$$

CREATE TRIGGER trg_review_no_delete BEFORE DELETE ON review FOR EACH ROW
BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Reviews cannot be deleted after submission.';
END$$

-- A purchase is valid only for someone else's currently active listing. The
-- unique purchase.itemId constraint provides the final one-buyer guarantee;
-- the application also locks the item row during checkout to avoid races.
CREATE TRIGGER trg_purchase_rules BEFORE INSERT ON purchase FOR EACH ROW
BEGIN
    IF EXISTS (SELECT 1 FROM item WHERE itemId = NEW.itemId AND seller = NEW.buyer) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'A seller cannot buy their own item.';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM item WHERE itemId = NEW.itemId AND status = 'active') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'This item is no longer available.';
    END IF;
END$$

-- Restore the normal statement delimiter for anything run after this file.
DELIMITER ;
