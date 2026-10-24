-- =============================================================================
-- 001_initial_schema.sql
-- Начальная схема БД для приложения «Инвентаризация»
-- Применяется один раз при развёртывании.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Триггерная функция: автоматически обновляет updated_at при UPDATE
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- =============================================================================
-- 1. procurement (Закупки)
-- =============================================================================
CREATE TABLE procurement (
    id                          BIGSERIAL PRIMARY KEY,

    code                        TEXT NOT NULL,
    okpd2                       TEXT,
    nomenclature                TEXT,
    qr_code                     TEXT,

    status                      TEXT,
    project                     TEXT,
    mto_service                 TEXT,

    price                       NUMERIC(15,2),
    quantity                    NUMERIC(12,3),
    amount                      NUMERIC(15,2),
    packaging                   TEXT,
    unit                        TEXT,
    plan_line                   TEXT,
    need_plan                   TEXT,
    mtr_plan                    TEXT,
    mto_department              TEXT,
    mto_curator                 TEXT,
    supplier_invoice_approved   TEXT,
    final_price                 NUMERIC(15,2),
    final_amount                NUMERIC(15,2),

    purchase_request            TEXT,
    payment_request             TEXT,
    receipt_order               TEXT,
    paid                        TEXT,
    received_to_warehouse       TEXT,
    cancelled                   TEXT,
    link                        TEXT,

    remainder                   NUMERIC(12,3),
    storage_location            TEXT,
    written_off                 TEXT,

    photo_path                  TEXT,

    row_version                 INT NOT NULL DEFAULT 1,
    is_deleted                  BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at                  TIMESTAMPTZ,
    deleted_by                  TEXT,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by                  TEXT,
    updated_by                  TEXT
);

CREATE INDEX idx_procurement_code ON procurement(code);
CREATE INDEX idx_procurement_qr_code ON procurement(qr_code);
CREATE INDEX idx_procurement_status ON procurement(status);
CREATE INDEX idx_procurement_storage ON procurement(storage_location);
CREATE INDEX idx_procurement_dept ON procurement(mto_department);
CREATE INDEX idx_procurement_project ON procurement(project);
CREATE INDEX idx_procurement_curator ON procurement(mto_curator);

CREATE TRIGGER trg_procurement_updated_at
BEFORE UPDATE ON procurement
FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- =============================================================================
-- 2. os_main (ОС Главная)
-- =============================================================================
CREATE TABLE os_main (
    id                          BIGSERIAL PRIMARY KEY,

    code                        TEXT NOT NULL,
    okpd2                       TEXT,
    nomenclature                TEXT,
    qr_code                     TEXT,

    status                      TEXT,
    project                     TEXT,
    mto_service                 TEXT,

    price                       NUMERIC(15,2),
    quantity                    NUMERIC(12,3),
    amount                      NUMERIC(15,2),
    packaging                   TEXT,
    unit                        TEXT,
    plan_line                   TEXT,
    need_plan                   TEXT,
    mtr_plan                    TEXT,
    mto_department              TEXT,
    mto_curator                 TEXT,
    supplier_invoice_approved   TEXT,
    final_price                 NUMERIC(15,2),
    final_amount                NUMERIC(15,2),

    purchase_request            TEXT,
    payment_request             TEXT,
    receipt_order               TEXT,
    paid                        TEXT,
    received_to_warehouse       TEXT,
    link                        TEXT,

    remainder                   NUMERIC(12,3),
    storage_location            TEXT,

    photo_path                  TEXT,

    row_version                 INT NOT NULL DEFAULT 1,
    is_deleted                  BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at                  TIMESTAMPTZ,
    deleted_by                  TEXT,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by                  TEXT,
    updated_by                  TEXT
);

CREATE INDEX idx_os_main_code ON os_main(code);
CREATE INDEX idx_os_main_qr_code ON os_main(qr_code);
CREATE INDEX idx_os_main_status ON os_main(status);
CREATE INDEX idx_os_main_storage ON os_main(storage_location);
CREATE INDEX idx_os_main_dept ON os_main(mto_department);
CREATE INDEX idx_os_main_project ON os_main(project);
CREATE INDEX idx_os_main_curator ON os_main(mto_curator);

CREATE TRIGGER trg_os_main_updated_at
BEFORE UPDATE ON os_main
FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- =============================================================================
-- 3. plastic_spools (Пластик)
-- =============================================================================
CREATE TABLE plastic_spools (
    id                  BIGSERIAL PRIMARY KEY,

    name                TEXT,
    type                TEXT,
    color               TEXT,
    weight              NUMERIC(12,3),
    qr_code             TEXT,
    code                TEXT NOT NULL,
    storage_location    TEXT,

    photo_path          TEXT,

    row_version         INT NOT NULL DEFAULT 1,
    is_deleted          BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at          TIMESTAMPTZ,
    deleted_by          TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by          TEXT,
    updated_by          TEXT
);

CREATE INDEX idx_plastic_code ON plastic_spools(code);
CREATE INDEX idx_plastic_qr_code ON plastic_spools(qr_code);
CREATE INDEX idx_plastic_type ON plastic_spools(type);
CREATE INDEX idx_plastic_storage ON plastic_spools(storage_location);

CREATE TRIGGER trg_plastic_updated_at
BEFORE UPDATE ON plastic_spools
FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- =============================================================================
-- 4. plastic_settings (Настройки печати пластика)
-- =============================================================================
CREATE TABLE plastic_settings (
    id              BIGSERIAL PRIMARY KEY,
    plastic_type    TEXT NOT NULL UNIQUE,
    nozzle_temp     NUMERIC(5,0),
    bed_temp        NUMERIC(5,0),
    fan_speed       NUMERIC(5,0),
    notes           TEXT
);