CREATE TABLE `roles` (
  `id` int PRIMARY KEY AUTO_INCREMENT,
  `key` varchar(32) UNIQUE NOT NULL
);

CREATE TABLE `users` (
  `id` int PRIMARY KEY AUTO_INCREMENT,
  `name` varchar(120) NOT NULL,
  `phone` varchar(32),
  `email` varchar(120),
  `role_id` int NOT NULL,
  `password_hash` varchar(255) NOT NULL,
  `active` boolean NOT NULL DEFAULT true,
  `created_at` datetime NOT NULL DEFAULT (CURRENT_TIMESTAMP)
);

CREATE TABLE `tables` (
  `id` int PRIMARY KEY AUTO_INCREMENT,
  `code` varchar(32) UNIQUE NOT NULL,
  `name` varchar(64),
  `status` ENUM ('FREE', 'OCCUPIED', 'CLEANING') NOT NULL DEFAULT 'FREE',
  `created_at` datetime NOT NULL DEFAULT (CURRENT_TIMESTAMP)
);

CREATE TABLE `table_sessions` (
  `id` int PRIMARY KEY AUTO_INCREMENT,
  `table_id` int NOT NULL,
  `order_id` int,
  `opened_by` int,
  `opened_at` datetime NOT NULL DEFAULT (CURRENT_TIMESTAMP),
  `closed_at` datetime
);

CREATE TABLE `menu_categories` (
  `id` int PRIMARY KEY AUTO_INCREMENT,
  `name` varchar(120) NOT NULL,
  `sort` int NOT NULL DEFAULT 0,
  `active` boolean NOT NULL DEFAULT true
);

CREATE TABLE `menu_items` (
  `id` int PRIMARY KEY AUTO_INCREMENT,
  `category_id` int NOT NULL,
  `name` varchar(160) NOT NULL,
  `description` text,
  `base_price` decimal(10,2) NOT NULL,
  `photo_url` varchar(255),
  `is_available` boolean NOT NULL DEFAULT true,
  `options_schema_json` json,
  `sort` int NOT NULL DEFAULT 0
);

CREATE TABLE `orders` (
  `id` int PRIMARY KEY AUTO_INCREMENT,
  `code` varchar(40) UNIQUE,
  `table_id` int,
  `channel` ENUM ('DINE_IN', 'STAFF_POS') NOT NULL DEFAULT 'DINE_IN',
  `status` ENUM ('OPEN', 'SUBMITTED', 'PARTIAL_READY', 'READY', 'SERVED', 'BILLED', 'PAID', 'CANCELLED') NOT NULL DEFAULT 'OPEN',
  `subtotal` decimal(10,2) NOT NULL DEFAULT 0,
  `service_charge_pct` decimal(5,4) NOT NULL DEFAULT 0.1,
  `service_charge_amt` decimal(10,2) NOT NULL DEFAULT 0,
  `vat_pct` decimal(5,4) NOT NULL DEFAULT 0.07,
  `vat_amt` decimal(10,2) NOT NULL DEFAULT 0,
  `discount_amt` decimal(10,2) NOT NULL DEFAULT 0,
  `grand_total` decimal(10,2) NOT NULL DEFAULT 0,
  `created_by` int,
  `created_at` datetime NOT NULL DEFAULT (CURRENT_TIMESTAMP),
  `closed_at` datetime,
  `note` text
);

CREATE TABLE `order_items` (
  `id` int PRIMARY KEY AUTO_INCREMENT,
  `order_id` int NOT NULL,
  `menu_item_id` int NOT NULL,
  `name_snapshot` varchar(160) NOT NULL,
  `qty` int NOT NULL,
  `unit_price` decimal(10,2) NOT NULL,
  `options_json` json,
  `notes` varchar(255),
  `status` ENUM ('PENDING', 'COOKING', 'READY', 'SERVED', 'VOID') NOT NULL DEFAULT 'PENDING',
  `line_total` decimal(10,2) NOT NULL,
  `printed` boolean NOT NULL DEFAULT false,
  `created_at` datetime NOT NULL DEFAULT (CURRENT_TIMESTAMP)
);

CREATE TABLE `bills` (
  `id` int PRIMARY KEY AUTO_INCREMENT,
  `order_id` int NOT NULL,
  `bill_no` varchar(40) UNIQUE NOT NULL,
  `subtotal` decimal(10,2) NOT NULL,
  `service_charge_amt` decimal(10,2) NOT NULL,
  `vat_amt` decimal(10,2) NOT NULL,
  `discount_amt` decimal(10,2) NOT NULL,
  `grand_total` decimal(10,2) NOT NULL,
  `paid_status` ENUM ('UNPAID', 'PAID', 'VOID') NOT NULL DEFAULT 'UNPAID',
  `created_at` datetime NOT NULL DEFAULT (CURRENT_TIMESTAMP),
  `paid_at` datetime
);

CREATE TABLE `payments` (
  `id` int PRIMARY KEY AUTO_INCREMENT,
  `bill_id` int NOT NULL,
  `method` ENUM ('CASH', 'TRANSFER', 'PROMPTPAY', 'CARD') NOT NULL,
  `amount` decimal(10,2) NOT NULL,
  `reference` varchar(120),
  `created_at` datetime NOT NULL DEFAULT (CURRENT_TIMESTAMP)
);

CREATE TABLE `staff_calls` (
  `id` int PRIMARY KEY AUTO_INCREMENT,
  `table_id` int NOT NULL,
  `order_id` int,
  `type` ENUM ('CALL_STAFF', 'WATER', 'BILL', 'OTHER') NOT NULL DEFAULT 'CALL_STAFF',
  `message` varchar(160),
  `status` ENUM ('OPEN', 'ACK', 'DONE') NOT NULL DEFAULT 'OPEN',
  `created_at` datetime NOT NULL DEFAULT (CURRENT_TIMESTAMP),
  `resolved_by` int,
  `resolved_at` datetime
);

CREATE TABLE `audit_logs` (
  `id` int PRIMARY KEY AUTO_INCREMENT,
  `user_id` int,
  `action` varchar(64) NOT NULL,
  `entity` varchar(64) NOT NULL,
  `entity_id` int NOT NULL,
  `payload_json` json,
  `created_at` datetime NOT NULL DEFAULT (CURRENT_TIMESTAMP)
);

CREATE INDEX `idx_users_email` ON `users` (`email`);

CREATE INDEX `menu_items_index_1` ON `menu_items` (`category_id`, `sort`);

CREATE INDEX `orders_index_2` ON `orders` (`table_id`);

CREATE INDEX `orders_index_3` ON `orders` (`status`);

CREATE INDEX `orders_index_4` ON `orders` (`created_at`);

CREATE INDEX `order_items_index_5` ON `order_items` (`order_id`);

CREATE INDEX `order_items_index_6` ON `order_items` (`status`);

CREATE INDEX `bills_index_7` ON `bills` (`order_id`);

CREATE INDEX `bills_index_8` ON `bills` (`paid_status`, `paid_at`);

CREATE INDEX `payments_index_9` ON `payments` (`bill_id`);

CREATE INDEX `staff_calls_index_10` ON `staff_calls` (`table_id`, `status`);

CREATE INDEX `staff_calls_index_11` ON `staff_calls` (`order_id`);

CREATE INDEX `audit_logs_index_12` ON `audit_logs` (`entity`, `entity_id`);

CREATE INDEX `audit_logs_index_13` ON `audit_logs` (`user_id`, `created_at`);

ALTER TABLE `users` ADD FOREIGN KEY (`role_id`) REFERENCES `roles` (`id`);

ALTER TABLE `table_sessions` ADD FOREIGN KEY (`table_id`) REFERENCES `tables` (`id`);

ALTER TABLE `table_sessions` ADD FOREIGN KEY (`order_id`) REFERENCES `orders` (`id`);

ALTER TABLE `table_sessions` ADD FOREIGN KEY (`opened_by`) REFERENCES `users` (`id`);

ALTER TABLE `menu_items` ADD FOREIGN KEY (`category_id`) REFERENCES `menu_categories` (`id`);

ALTER TABLE `orders` ADD FOREIGN KEY (`table_id`) REFERENCES `tables` (`id`);

ALTER TABLE `orders` ADD FOREIGN KEY (`created_by`) REFERENCES `users` (`id`);

ALTER TABLE `order_items` ADD FOREIGN KEY (`order_id`) REFERENCES `orders` (`id`);

ALTER TABLE `order_items` ADD FOREIGN KEY (`menu_item_id`) REFERENCES `menu_items` (`id`);

ALTER TABLE `bills` ADD FOREIGN KEY (`order_id`) REFERENCES `orders` (`id`);

ALTER TABLE `payments` ADD FOREIGN KEY (`bill_id`) REFERENCES `bills` (`id`);

ALTER TABLE `staff_calls` ADD FOREIGN KEY (`table_id`) REFERENCES `tables` (`id`);

ALTER TABLE `staff_calls` ADD FOREIGN KEY (`order_id`) REFERENCES `orders` (`id`);

ALTER TABLE `staff_calls` ADD FOREIGN KEY (`resolved_by`) REFERENCES `users` (`id`);

ALTER TABLE `audit_logs` ADD FOREIGN KEY (`user_id`) REFERENCES `users` (`id`);
