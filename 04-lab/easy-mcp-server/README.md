# Repo Helper MCP Server — Bài 1 và Bài 2

## Công việc thực tế

Khi làm việc với một repository, hai thao tác phải làm thủ công nhiều lần là:

1. tìm file theo tên hoặc loại file;
2. tìm một đoạn text trong code và tài liệu để biết logic nằm ở đâu hoặc kiểm tra
   một cấu hình đã xuất hiện ở những file nào.

Server này biến hai thao tác đó thành MCP tools để Claude Code có thể thực hiện
trực tiếp trên workspace. Kết quả được đọc từ file thật, không phải dữ liệu giả.

## Tools

### `find_files`

Tìm file bên trong `WORKSPACE_ROOT`.

| Input | Kiểu | Mặc định | Ý nghĩa |
|---|---|---:|---|
| `name_pattern` | `string` | `*` | Ví dụ `*.py`, `README*`, `04-lab/**/*.md` |
| `max_results` | `integer` | `50` | Số kết quả, tối đa 200 |
| `include_hidden` | `boolean` | `false` | Có tìm trong file/thư mục bắt đầu bằng `.` không |

Output là JSON gồm `workspace`, `pattern`, danh sách path tương đối trong
`files`, và `truncated`.

Ví dụ yêu cầu Claude Code:

> Tìm tối đa 20 file Python trong repo.

### `search_in_files`

Tìm một chuỗi phân biệt hoa thường trong các file text.

| Input | Kiểu | Bắt buộc | Ý nghĩa |
|---|---|---:|---|
| `query` | `string` | Có | Chuỗi cần tìm |
| `file_pattern` | `string` | Không | Lọc file, mặc định `*` |
| `max_results` | `integer` | Không | Số dòng khớp, tối đa 200 |
| `include_hidden` | `boolean` | Không | Tìm cả file ẩn nếu `true` |

Output là JSON gồm `matches`; mỗi match có `file`, `line`, `text`. File nhị
phân và file lớn hơn 2 MB được bỏ qua. Server chỉ trả path tương đối nên Claude
Code không phải xử lý đường dẫn tuyệt đối.

Ví dụ:

> Tìm tất cả nơi dùng `FastMCP` trong các file Python.

## Cài đặt và chạy

Yêu cầu Python 3.10+ và `uv` (hoặc `pip`). Từ thư mục này:

```bash
uv sync
```

Chọn repository mà server được phép đọc bằng `WORKSPACE_ROOT`:

```bash
# PowerShell
$env:WORKSPACE_ROOT = "D:\\AITHUCCHIEN\\Day26-2A202601208-NguyenBuiAnhTuan"
uv run python repo_server.py

# macOS/Linux
export WORKSPACE_ROOT="/duong/dan/toi/repository"
uv run python repo_server.py
```

Server Bài 2 mặc định dùng `streamable-http`. Để chạy smoke test Bài 1 qua
stdio, đặt `MCP_TRANSPORT=stdio` trước khi chạy. Không đưa `print()` debug ra
stdout vì stdout là kênh giao tiếp MCP.

## Đăng ký Bài 1 với Claude Code (stdio)

Chạy lệnh sau từ bất kỳ terminal nào, thay đường dẫn bằng đường dẫn tuyệt đối
của repo:

```bash
claude mcp add repo-helper --env WORKSPACE_ROOT=D:\\AITHUCCHIEN\\Day26-2A202601208-NguyenBuiAnhTuan MCP_TRANSPORT=stdio -- python D:\\AITHUCCHIEN\\Day26-2A202601208-NguyenBuiAnhTuan\\04-lab\\easy-mcp-server\\repo_server.py
```

Nếu dùng `uv`, có thể đăng ký bằng:

```bash
claude mcp add repo-helper --env WORKSPACE_ROOT=D:\\AITHUCCHIEN\\Day26-2A202601208-NguyenBuiAnhTuan MCP_TRANSPORT=stdio -- uv run --directory D:\\AITHUCCHIEN\\Day26-2A202601208-NguyenBuiAnhTuan\\04-lab\\easy-mcp-server python repo_server.py
```

Kiểm tra server đã được đăng ký:

```bash
claude mcp list
```

Sau đó mở Claude Code trong repo và thử:

```text
Hãy dùng repo-helper để tìm các file README trong repository.
Hãy dùng repo-helper tìm chuỗi "FastMCP" trong các file Python và giải thích các dòng tìm được.
```

## Kiểm tra bằng MCP client không cần API key

Smoke test thực hiện đúng hai bước MCP quan trọng: `list_tools` để khám phá
tool và `call_tool` để gọi server qua stdio.

```bash
uv run python test_server.py
```

Kết quả thành công:

```text
MCP smoke test passed
Discovered tools: find_files, search_in_files
```

## Bài 2 — Authentication qua Streamable HTTP

Server mặc định chạy bằng `streamable-http` tại `http://localhost:8085/mcp` và
kiểm tra Bearer token trước khi cho phép MCP client khám phá hoặc gọi tool.
Token có quyền `repo:read` mới được phép truy cập.

### Chạy server HTTP

```bash
# PowerShell
$env:WORKSPACE_ROOT = "D:\\AITHUCCHIEN\\Day26-2A202601208-NguyenBuiAnhTuan"
$env:MCP_AUTH_TOKEN = "your-long-random-token"
$env:MCP_LIMITED_TOKEN = "limited-token-for-403-test"
$env:MCP_TRANSPORT = "streamable-http"
$env:PORT = "8085"
uv run python repo_server.py

# macOS/Linux
export WORKSPACE_ROOT="/duong/dan/toi/repository"
export MCP_AUTH_TOKEN="your-long-random-token"
export MCP_LIMITED_TOKEN="limited-token-for-403-test"
export MCP_TRANSPORT="streamable-http"
export PORT="8085"
uv run python repo_server.py
```

`MCP_AUTH_TOKEN` là token hợp lệ với scope `repo:read`. Token trong
`MCP_LIMITED_TOKEN` được nhận diện nhưng không có scope, dùng để kiểm tra
trường hợp bị từ chối do thiếu quyền. Nếu không cấu hình, server dùng token
demo `repo-dev-token` và `repo-limited-token`.

### Kiểm tra các trường hợp auth

```bash
uv run python test_auth.py
```

Test này tự khởi động một server ở port `8765` và kiểm tra:

| Trường hợp | Kết quả mong đợi |
|---|---|
| Không có `Authorization` | HTTP `401` hoặc `403` |
| Bearer token sai | HTTP `401` hoặc `403` |
| Token đúng nhưng thiếu `repo:read` | HTTP `401` hoặc `403` |
| Token đúng và đủ quyền | HTTP `200`, sau đó `list_tools`/`call_tool` thành công |

Kết quả thành công mẫu:

```text
HTTP auth test passed
No token: 401
Wrong token: 401
Limited token: 403
Valid token: 200
Authenticated MCP call: passed
```

### Kết nối từ Claude Code qua HTTP

Khởi động server HTTP trước, sau đó đăng ký endpoint bằng token hợp lệ:

```bash
claude mcp add repo-helper-http --scope project --transport http http://127.0.0.1:8085/mcp --header "Authorization: Bearer your-long-random-token"
claude mcp list
```

Trong Claude Code, thử:

```text
Hãy dùng repo-helper-http gọi find_files với pattern "*.py" và tối đa 10 kết quả.
```

Không đưa token thật vào Git hoặc README. Nếu đổi token, xóa server cũ bằng
`claude mcp remove repo-helper-http` rồi đăng ký lại.

### Thử trong mạng LAN

Server đã bind vào `0.0.0.0`, nên máy khác có thể kết nối nếu firewall cho phép
port `8085`:

1. Trên máy chạy server, lấy IP LAN bằng `ipconfig` (Windows) hoặc `ip addr`.
2. Mở TCP port `8085` trên firewall nếu cần.
3. Từ máy client, dùng header `Authorization: Bearer <MCP_AUTH_TOKEN>` khi
   kết nối tới `http://<IP-LAN>:8085/mcp`.
4. Đăng ký Claude Code bằng endpoint:

```bash
claude mcp add repo-helper-lan --scope project --transport http http://<IP-LAN>:8085/mcp --header "Authorization: Bearer <MCP_AUTH_TOKEN>"
```

Có thể đặt `MCP_PUBLIC_URL=http://<IP-LAN>:8085` khi chạy server để metadata
auth sử dụng đúng địa chỉ LAN. Trong môi trường hiện tại mình kiểm tra
localhost; kiểm tra từ máy thứ hai cần thực hiện trên cùng mạng LAN thật.

## Giới hạn an toàn

- Server chỉ đọc bên trong `WORKSPACE_ROOT`.
- Không đi theo symlink và bỏ qua `.git`, `.venv`, `node_modules`, cache Python.
- Mỗi tool giới hạn tối đa 200 kết quả.
- Tool tìm nội dung bỏ qua file nhị phân và file lớn hơn 2 MB.
- Server không sửa, xóa hoặc gửi dữ liệu ra dịch vụ bên ngoài.
