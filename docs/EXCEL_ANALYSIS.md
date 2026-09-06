# Excel Workbook Analysis — `file.xlsx`

Source: [b-lincko/excel-dashboard `file.xlsx`](https://github.com/b-lincko/excel-dashboard/blob/main/file.xlsx)

This is **Linkco (Al Rawabet Commercial Services and Contracting Co. W.L.L.)**’s live **Material Request (MR) log** tied to **IM Work Orders**. It is the dashboard’s source of truth. The workbook is **not** redesigned.

## 1. Worksheets

| Sheet | Role |
| ----- | ---- |
| **Linkco_MR_Log (SH5 & SH1)** | Data — Shield 5 & Shield 1 (~1,980 MRs). Excel table `Table1` `A3:T11112` |
| **SH1 & SH5 - REPORT** | Procurement report (formulas / charts) — **never written by the app** |
| **Linkco_MR_Log (F5)** | Data — Falcon 5 (~202 MRs). Excel table `Table16` |
| **F5 - REPORT** | Falcon 5 report — **never written** |
| **File Pah** / **File Pah (F5)** | UNC paths used by hyperlink formulas |

KPI `COUNTIF` formulas live in **rows 1–2** of each log sheet (`OPEN`, `CLOSED`, `PLACED`, `UNDER NTP`, `UNDER GATEPASS`, `ON HOLD`). They are preserved.

## 2. Columns (header **row 3**, data from **row 4**)

| Excel column | Application field | Notes |
| ------------ | ----------------- | ----- |
| SN | *(formula, not mapped)* | `=IF(B4>0,ROW()-3,"")` — **never overwritten** |
| IM Work Order # | `work_order_id` | IM WO number (numeric on SH, `LKF5-nnnn` on F5). **Not unique** — one WO can have several MRs |
| WO Priority Level | `priority` | LOW / MEDIUM / HIGH (mixed case on SH) |
| IM WO Completion | `completion_date` | Date or `N/A` |
| MR Received Date | `created_date` | When the material request was logged |
| Assign to | `assigned_to` | Nesar, Arun, Abubacar, Yousuf |
| Purchase Type | `work_type` | Local PO, Direct Cash, Service, International, Under Warranty, Emergency |
| Due date (Approx. 2 weeks) | `due_date` | **Array formula** from purchase type + MR date — computed in the app, **never overwritten** |
| WO Asset Name | `location` | Asset / location code |
| Required Material Details | `description` | What was requested |
| STATUS | `status` | OPEN, PLACED, CLOSED, UNDER NTP, UNDER GATEPASS, ON HOLD |
| Date of PO / Expected PO / RFQ Sent | `scheduled_date` | |
| Supplier Name | `supplier` | |
| ETA / Expected Date of RFQ Response | `closed_date` | Used as ETA / close proxy |
| Delivery Status | `issue` / `delay_reason` | Delivered, Pending, Estimation Provided, Material in Store |
| REMARKS / NOTES | `remarks` | Why delayed / progress |
| PO NO # | `po_number` | |
| Server Link / Link Path - 1 / Link Path | *(formulas)* | Hyperlinks to the file server — **never overwritten** |

Site (`department`) is derived from the worksheet: `SH5-SH1` or `F5`.

Row identity for updates: `record_id` = `{site}:{excel_row}` (e.g. `SH5-SH1:13`). Updates never insert a second row for an existing record.

## 3. Work-order ID

`IM Work Order #` is the business identifier.

It is **not unique** (79 duplicate WO numbers on SH5 & SH1 — multiple material lines per IM WO). Synchronization keys off **sheet + row**.

## 4. Dates

| Role | Column |
| ---- | ------ |
| Created | MR Received Date |
| Due | Formula: Direct Cash +3d, Local PO +5d, International/Service/Warranty +10d, Emergency +0, else +14d |
| WO completion | IM WO Completion |
| PO / RFQ | Date of PO / Expected PO / RFQ Sent |
| ETA | ETA / Expected Date of RFQ Response |

**Overdue:** due date (computed) &lt; today AND STATUS ≠ CLOSED.

**Aging:** today − MR Received Date (open MRs).

**Average closing:** ETA − MR Received Date on CLOSED rows (when ETA is a date).

## 5. Status (from Excel, not hard-coded)

CLOSED · OPEN · PLACED · UNDER NTP · UNDER GATEPASS · ON HOLD

Configurable closed set: **CLOSED** only.

- Open = not CLOSED  
- Pending = OPEN, UNDER NTP, ON HOLD  
- In progress = PLACED, UNDER GATEPASS  

## 6. Why MRs are not closed

Open rows are grouped by **STATUS** (and delivery status when it is not “Delivered”), e.g. `UNDER NTP — Estimation Provided`, `PLACED — Pending`.

## 7. Department / technician

- Site: SH5-SH1 vs F5 (worksheet)  
- Technician: Assign to  
- Category: Purchase Type  
- Asset: WO Asset Name  

There is no separate “department” column.

## 8. Missing / special fields

No explicit “closing date” or “delay reason” column. ETA and Delivery Status / STATUS are used instead. Validation does **not** require a close date on CLOSED rows (`require_closed_date_on_close = false`). Open rows may have an ETA (`allow_open_with_close_date = true`).

## 9. Synchronization risks (mitigated)

| Risk | Mitigation |
| ---- | ---------- |
| Duplicate IM WO # | Identity is sheet + row (`record_id`) |
| Formula destruction | SN, due date, hyperlinks never written; report sheets untouched |
| Title KPI rows | Header row = 3; rows 1–2 left alone |
| Huge table range (`T11112`) | Empty rows skipped; table ref not rewritten |
| 4 MB workbook | In-memory cache; backup before every write; ~3s save |
| Concurrent Excel use | file lock + HTTP 423 |
| External edits | sync token / HTTP 409 |

Defined names in the workbook (`ClientName`, `Discipline_Type`, `Enquiry_Type`, `RFI_Status`) are unused leftover names and are left as-is.
