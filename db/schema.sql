-- SmartLedger SQLite Schema

PRAGMA foreign_keys = ON;

------------------------------------------------------------
-- 기존 테이블 초기화 (개발 중 재생성 용도)
------------------------------------------------------------
DROP VIEW IF EXISTS v_month_category_totals;
DROP VIEW IF EXISTS v_month_totals;
DROP TRIGGER IF EXISTS trg_receipts_updated_at;
DROP TABLE IF EXISTS alerts;
DROP TABLE IF EXISTS budgets;
DROP TABLE IF EXISTS category_rules;
DROP TABLE IF EXISTS receipt_items;
DROP TABLE IF EXISTS receipts;
DROP TABLE IF EXISTS users;

------------------------------------------------------------
-- 사용자 정보 (시연용 단일 계정)
------------------------------------------------------------
CREATE TABLE users (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  email         TEXT UNIQUE NOT NULL,
  password_hash TEXT,
  created_at    TEXT DEFAULT (datetime('now'))
);

------------------------------------------------------------
-- 영수증 본문
------------------------------------------------------------
CREATE TABLE receipts (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id       INTEGER NOT NULL,
  merchant      TEXT NOT NULL,
  total         INTEGER NOT NULL CHECK(total >= 0),
  purchased_at  TEXT NOT NULL,                 -- YYYY-MM-DD
  status        TEXT NOT NULL CHECK(status IN ('PENDING','CONFIRMED')),
  image_path    TEXT,                          -- OCR 원본 파일 경로 (선택)
  created_at    TEXT DEFAULT (datetime('now')),
  updated_at    TEXT DEFAULT (datetime('now')),
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 중복 방지 (동일 사용자+상호+날짜+합계)
CREATE UNIQUE INDEX IF NOT EXISTS uq_receipt_dedup
ON receipts(user_id, merchant, total, purchased_at);

-- 주요 인덱스
CREATE INDEX idx_receipts_user ON receipts(user_id);
CREATE INDEX idx_receipts_date ON receipts(purchased_at);
CREATE INDEX idx_receipts_merchant ON receipts(merchant);
CREATE INDEX idx_receipts_status ON receipts(status);

------------------------------------------------------------
-- 영수증 품목
------------------------------------------------------------
CREATE TABLE receipt_items (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  receipt_id  INTEGER NOT NULL,
  name        TEXT NOT NULL,
  qty         INTEGER NOT NULL DEFAULT 1 CHECK(qty > 0),
  price       INTEGER NOT NULL DEFAULT 0 CHECK(price >= 0),
  category    TEXT,                            -- 자동 분류 결과
  subtotal    INTEGER GENERATED ALWAYS AS (qty * price) VIRTUAL,
  FOREIGN KEY (receipt_id) REFERENCES receipts(id) ON DELETE CASCADE
);

CREATE INDEX idx_items_receipt ON receipt_items(receipt_id);
CREATE INDEX idx_items_category ON receipt_items(category);

------------------------------------------------------------
-- 카테고리 룰 (가산점 기능)
------------------------------------------------------------
CREATE TABLE category_rules (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  keyword         TEXT NOT NULL,               -- ex) '스타벅스', '우유'
  mapped_category TEXT NOT NULL,               -- ex) '카페', '유제품'
  priority        INTEGER NOT NULL DEFAULT 100 -- 낮을수록 우선 적용
);

CREATE INDEX idx_rules_keyword ON category_rules(keyword);
CREATE INDEX idx_rules_priority ON category_rules(priority);

------------------------------------------------------------
-- 예산 (가산점 기능)
------------------------------------------------------------
CREATE TABLE budgets (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id  INTEGER NOT NULL,
  category TEXT NOT NULL,
  month    TEXT NOT NULL,                      -- YYYY-MM
  amount   INTEGER NOT NULL DEFAULT 0 CHECK(amount >= 0),
  UNIQUE(user_id, category, month),
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

------------------------------------------------------------
-- 알림 (가산점 기능)
------------------------------------------------------------
CREATE TABLE alerts (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id             INTEGER NOT NULL,
  type                TEXT NOT NULL CHECK(type IN ('overspend','anomaly','fixed_detected')),
  message             TEXT NOT NULL,
  created_at          TEXT DEFAULT (datetime('now')),
  related_receipt_id  INTEGER,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (related_receipt_id) REFERENCES receipts(id) ON DELETE CASCADE
);

------------------------------------------------------------
-- 대시보드용 뷰 (월별 합계 & 카테고리별 합계)
------------------------------------------------------------
CREATE VIEW v_month_totals AS
SELECT
  substr(purchased_at, 1, 7) AS month,  -- YYYY-MM
  SUM(total) AS month_total
FROM receipts
WHERE status = 'CONFIRMED'
GROUP BY substr(purchased_at, 1, 7);

CREATE VIEW v_month_category_totals AS
SELECT
  substr(r.purchased_at, 1, 7) AS month,
  COALESCE(ri.category, '미분류') AS category,
  SUM(ri.qty * ri.price) AS category_total
FROM receipts r
JOIN receipt_items ri ON ri.receipt_id = r.id
WHERE r.status = 'CONFIRMED'
GROUP BY substr(r.purchased_at, 1, 7), COALESCE(ri.category, '미분류');

------------------------------------------------------------
-- updated_at 자동 갱신 트리거
------------------------------------------------------------
CREATE TRIGGER trg_receipts_updated_at
AFTER UPDATE ON receipts
FOR EACH ROW
BEGIN
  UPDATE receipts
  SET updated_at = datetime('now')
  WHERE id = NEW.id;
END;

                    