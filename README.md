# QID ↔ EID Lookup Tool

Công cụ tra cứu offline cho dữ liệu mapping của IBM QRadar. Tool hỗ trợ cả dòng lệnh (CLI) và giao diện desktop (GUI), với ba chế độ tra cứu chính:

1. **QID lookup**: biết QRadar QID, tìm EID và thông tin event tương ứng.
2. **EID lookup**: biết vendor Event ID, tìm QID tương ứng.
3. **High Level/Low Level Category lookup**: tìm toàn bộ QID/EID thuộc một QRadar category.

Mọi truy vấn chạy trên SQLite cục bộ. Sau khi import dữ liệu, tool không cần kết nối Internet hoặc QRadar.

## Chọn đúng chế độ lookup

| Thông tin đang có | Chế độ cần dùng | Ví dụ |
|---|---|---|
| QRadar QID | QID Lookup | `5000849` |
| Windows Event ID hoặc vendor Event ID | EID Lookup | `7045`, `4688`, `4662` |
| Low Level Category, có thể kèm High Level Category | Category Lookup | `Audit.Command Execution Success` |

> [!IMPORTANT]
> Windows Event ID `7045` là **EID**, không phải QID. Hãy nhập nó trong tab **EID Lookup**. Trong dataset hiện tại, EID `7045` có nhiều mapping; mapping Windows với Device Type `12` trỏ tới QID `5001613` (`A service was installed in a system`).

QID và EID không phải quan hệ một-một. Một QID/EID có thể xuất hiện trong nhiều Device Type, vì vậy tool luôn trả về tất cả mapping phù hợp.

## Tính năng

- Tra cứu một hoặc nhiều QID/EID.
- Lọc theo Device Type khi một ID có nhiều mapping.
- Tra cứu chính xác theo High Level Category và/hoặc Low Level Category.
- Tìm kiếm theo từ khóa trong event name, description và category.
- Xuất kết quả ra JSON, CSV hoặc TSV.
- Import CSV theo kiểu thêm dữ liệu hoặc thay thế database an toàn bằng `--replace`.
- Cùng một lookup engine cho CLI và GUI nên kết quả hai chế độ là như nhau.

## Cài đặt

Yêu cầu Python 3.9 trở lên.

```powershell
git clone https://github.com/bruning-frighting/qid-eid-lookup.git
cd qid-eid-lookup
python -m pip install .
```

Kiểm tra cài đặt:

```powershell
qidlookup --help
```

Nếu PowerShell không tìm thấy lệnh `qidlookup`, dùng:

```powershell
python -m qidlookup --help
```

## Chuẩn bị database

File `data/qid_eid.db` không được lưu trên GitHub vì database thật có dung lượng lớn. Sau khi clone repo, cần import CSV trước khi lookup.

### Chạy thử với CSV mẫu

Repo có file `data/raw/qid_eid_mapping.csv` gồm một số mapping mẫu:

```powershell
qidlookup import data/raw/qid_eid_mapping.csv --replace
```

CSV mẫu chỉ có 6 cột cơ bản, vì vậy dùng được cho QID/EID lookup nhưng **không có dữ liệu High/Low Level Category**.

### Import dataset đầy đủ

```powershell
qidlookup import path/to/qid_eid_full_mapping.csv --replace
```

Thứ tự tìm database:

1. `--database PATH`
2. Biến môi trường `QIDLOOKUP_DATABASE`
3. `data/qid_eid.db`

Ví dụ dùng database ở vị trí khác:

```powershell
qidlookup --database D:\QRadar\qid_eid.db eid 7045
```

## 1. QID Lookup

Dùng chế độ này khi giá trị đầu vào là **QRadar QID**. Kết quả cho biết EID, Device Type, category và tên event tương ứng.

### CLI

Tra một QID:

```powershell
qidlookup qid 5000849
```

Với CSV mẫu, QID `5000849` trả về hai mapping cùng EID `4662`, nhưng thuộc hai Device Type khác nhau.

Tra nhiều QID:

```powershell
qidlookup qid 5000843 5000849 5000850
qidlookup qid --qids 5000843,5000849,5000850
qidlookup qid-list qids.txt
```

Lọc theo Device Type:

```powershell
qidlookup qid 5000849 --device-type 12
```

### GUI

1. Mở tab **QID Lookup**.
2. Nhập một hoặc nhiều QID, phân tách bằng dấu phẩy hoặc xuống dòng.
3. Nhập **Device Type** nếu muốn thu hẹp kết quả.
4. Bấm **Lookup QID**.

Nếu QID không tồn tại, GUI sẽ báo không tìm thấy thay vì tự chuyển nó thành EID.

## 2. EID Lookup

Dùng chế độ này khi đầu vào là **Event ID của Windows hoặc vendor/log source**. EID được lưu dưới dạng text nên không bắt buộc chỉ là số.

### CLI

```powershell
qidlookup eid 4662
qidlookup eid 7045
```

Tra nhiều EID:

```powershell
qidlookup eid 4656 4662 4663
qidlookup eid --eids 4656,4662,4663
qidlookup eid-list eids.txt
```

Lọc Windows Event ID `7045` theo Device Type `12`:

```powershell
qidlookup eid 7045 --device-type 12
```

Trong dataset đầy đủ hiện tại, truy vấn này trả về QID `5001613`.

### GUI

1. Mở tab **EID Lookup**.
2. Nhập một hoặc nhiều Event ID.
3. Nếu cần, nhập Device Type. Ví dụ `12` cho mapping Windows trong dataset hiện tại.
4. Bấm **Lookup EID**.

EID có thể trả về nhiều QID. Đây là hành vi bình thường do cùng một Event ID có thể được sử dụng bởi nhiều Device Type.

## 3. High Level/Low Level Category Lookup

Category Lookup tìm tất cả QID/EID thuộc một QRadar category. Chế độ này cần dataset có hai cột:

- `high_level_category`
- `low_level_category`

Việc so khớp là **chính xác và không phân biệt hoa/thường**. Đây không phải tìm kiếm theo từ khóa.

### CLI

Có ba cách tra category.

Chỉ dùng Low Level Category:

```powershell
qidlookup category "Command Execution Success"
```

Chỉ dùng High Level Category:

```powershell
qidlookup category --hlc Audit
```

Dùng đồng thời High Level và Low Level Category để có kết quả chính xác nhất:

```powershell
qidlookup category "Command Execution Success" --hlc Audit
```

Hoặc dùng dạng gộp `High Level.Low Level`:

```powershell
qidlookup category "Audit.Command Execution Success"
```

Hai lệnh cuối cùng là tương đương. Trong dataset hiện tại có `Audit.Command Execution Success`; không có `System.Command Execution Success`.

> [!NOTE]
> Một Low Level Category có thể nằm dưới nhiều High Level Category. Nếu chỉ nhập Low Level Category, tool sẽ trả về mapping từ tất cả High Level Category phù hợp. Hãy thêm `--hlc` khi cần phân biệt.

Không kết hợp cả hai kiểu nhập trong cùng một lệnh. Ví dụ, không dùng `"Audit.Command Execution Success" --hlc Audit`; hãy chọn dạng gộp hoặc `--hlc` riêng.

### GUI

1. Mở tab **Category Lookup**.
2. Nhập **Low Level Category**.
3. Nhập **High Level Category** nếu cần phân biệt.
4. Có thể nhập thẳng `Audit.Command Execution Success` trong ô Low Level và để trống ô High Level; GUI sẽ tự tách hai phần.
5. Có thể thêm Device Type để lọc kết quả.
6. Bấm **Lookup**.

GUI hiển thị toàn bộ mapping và tóm tắt danh sách QID/EID duy nhất.

## Khởi chạy GUI

```powershell
qidlookup gui
```

Hoặc:

```powershell
qidlookup-gui
```

GUI gồm các tab:

- **QID Lookup**
- **EID Lookup**
- **Category Lookup**
- **Search**
- **Import CSV**
- **Stats**

Đường dẫn database đang dùng được hiển thị ở phía trên. Dùng **Browse...** và **Open** để chọn database khác.

## Search

Lệnh `search` dùng khi không biết chính xác QID, EID hoặc category:

```powershell
qidlookup search "service was installed"
qidlookup search "command execution"
qidlookup search "command" --hlc Audit
qidlookup search "service" --device-type 12 --limit 50
```

`search` tìm chuỗi con trong `event_name`, `description`, `event_category`, `high_level_category` và `low_level_category`. Các filter `--category`, `--hlc` và `--llc` là filter chính xác.

## Xuất kết quả

Các lệnh lookup hỗ trợ `human`, `json`, `csv` và `tsv`:

```powershell
qidlookup eid 7045 --format json
qidlookup qid 5000849 --format csv --output result.csv
qidlookup category "Audit.Command Execution Success" --format json --output category.json
```

Dùng `--force` nếu muốn ghi đè file đã tồn tại.

Trong GUI, bấm **Export kết quả...** sau khi lookup.

## Cấu trúc CSV

Sáu cột bắt buộc:

```text
devicetypeid,eid,event_category,qid,event_name,description
```

Các cột tùy chọn:

```text
severity,high_level_category,low_level_category
```

Header khuyến nghị cho dataset đầy đủ:

```csv
devicetypeid,eid,event_category,qid,event_name,description,severity,high_level_category,low_level_category
```

Nếu CSV không có High/Low Level Category, QID/EID lookup vẫn hoạt động bình thường; chỉ Category Lookup không có dữ liệu để trả về.

Schema nội bộ của QRadar có thể khác nhau giữa các phiên bản. Trước khi export trực tiếp từ PostgreSQL, hãy kiểm tra cấu trúc `qid_eid_mapping`, `qidmap` và `category_type` trên hệ thống của bạn. Mục tiêu là xuất đúng chín cột trong header trên.

## Kiểm tra database

```powershell
qidlookup stats
qidlookup validate
```

- `stats`: số mapping, QID/EID duy nhất, Device Type, category và dữ liệu thiếu.
- `validate`: kiểm tra schema, index và tính toàn vẹn SQLite.

## Exit code CLI

| Exit code | Ý nghĩa |
|---|---|
| `0` | Tìm thấy tất cả giá trị yêu cầu |
| `1` | Có ít nhất một giá trị không tìm thấy |
| `2` | Input hoặc option không hợp lệ |
| `3` | Lỗi database hoặc hệ thống |

## Xử lý sự cố

| Hiện tượng | Cách xử lý |
|---|---|
| Nhập `7045` trong QID Lookup nhưng không có kết quả | `7045` là EID; chuyển sang EID Lookup. |
| Một EID trả về nhiều QID | Lọc thêm Device Type; đây là quan hệ many-to-many bình thường. |
| Category Lookup không có kết quả | Kiểm tra CSV/database có `high_level_category` và `low_level_category` hay không. |
| `System.Command Execution Success` không tìm thấy | Dataset hiện tại chỉ có `Audit.Command Execution Success`. |
| Cùng LLC trả về nhiều nhóm | Thêm HLC bằng `--hlc` hoặc dạng `HLC.LLC`. |
| `qidlookup: command not found` | Dùng `python -m qidlookup ...` hoặc thêm Python Scripts vào `PATH`. |
| Database không đúng | Kiểm tra đường dẫn ở thanh trên GUI hoặc dùng `--database PATH` trong CLI. |
| File output đã tồn tại | Thêm `--force` hoặc chọn tên file khác. |

## Phát triển và test

```powershell
python -m pip install -e ".[dev]"
python -m pytest
python -m pytest --cov=qidlookup --cov-report=term-missing
```

Kiến trúc chính:

```text
CSV -> importer -> SQLite repository -> lookup/search services -> CLI hoặc GUI
```

- `src/qidlookup/core`: logic lookup và search.
- `src/qidlookup/database`: kết nối, schema và truy vấn SQLite.
- `src/qidlookup/cli`: giao diện dòng lệnh.
- `src/qidlookup/gui`: giao diện Tkinter.
- `src/qidlookup/importers` và `exporters`: import/export dữ liệu.
- `tests`: test cho importer, repository, lookup, search, formatting và CLI.

## Build Windows executable

```powershell
python -m pip install pyinstaller
pyinstaller --onefile --name qidlookup src/qidlookup/__main__.py
pyinstaller --onefile --windowed --name qidlookup-gui src/qidlookup/gui/app.py
```

Database không được nhúng tự động vào executable. Hãy để file `.db` bên cạnh executable hoặc chọn nó qua GUI/`--database`.

## License

MIT License. Xem [LICENSE](LICENSE).
