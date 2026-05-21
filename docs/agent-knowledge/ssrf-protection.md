# SSRF Protection（私网拦截）

> **何时读本文**：写网络工具或修改 validate_url 时
> **关联源码**：`packages/jay-agent-core/src/jay_agent_core/tools/base.py`

## 它解决什么问题

LLM 让用户给 Agent 一个 URL，再让 Agent 拉取——这是 SSRF（Server-Side Request Forgery）的经典温床。攻击者可以诱导 Agent 访问 `http://169.254.169.254/latest/meta-data/`（云元数据服务）、`http://localhost:6379/`（内网 Redis）、`http://192.168.1.1/admin`（内网设备），把云凭证或内网信息泄露给外部。本机制在请求发出前对 URL 做白盒校验，把这些目标拦在源头。

## 核心机制

1. **scheme 白名单**：只允许 `http` / `https`，其他（`file`、`gopher`、`ftp`、`ssh`）一律拒绝。
2. **hostname 黑名单**：`localhost`、`0.0.0.0` 默认拦截，可通过 `allow_private=True` 放行（仅测试场景）。
3. **元数据端点黑名单**：`169.254.169.254`、`metadata.google.internal`、`169.254.169.253` 永远拦截，不受 `allow_private` 影响。
4. **IP 段拦截**：`_BLOCKED_IP_RANGES` 涵盖 RFC1918 私网、loopback、link-local、IPv6 ULA / 链路本地。
5. **域名延迟校验**：纯域名（非 IP 直填）目前不解析 DNS，留给 `validate_redirect_url` 在跟随重定向时再次校验，防止 DNS rebinding。

## 关键代码锚点

| 文件 | 行号 | 角色 |
|---|---|---|
| `packages/jay-agent-core/src/jay_agent_core/tools/base.py` | L218-L230 | `_BLOCKED_IP_RANGES` 网段表 |
| `packages/jay-agent-core/src/jay_agent_core/tools/base.py` | L233-L237 | `_METADATA_ENDPOINTS` 元数据端点 |
| `packages/jay-agent-core/src/jay_agent_core/tools/base.py` | L240-L243 | `URLValidationError` 异常 |
| `packages/jay-agent-core/src/jay_agent_core/tools/base.py` | L246-L309 | `validate_url` 主校验逻辑 |
| `packages/jay-agent-core/src/jay_agent_core/tools/base.py` | L312-L334 | `validate_redirect_url` 重定向校验 |

## 常见陷阱

- **直接调 httpx 不过 validate_url**：网络工具实现时只看 happy path 测试通过就提交，忘了攻击向量。建议把 `validate_url(url)` 作为所有网络工具入口的第一行。
- **DNS rebinding**：当前实现允许域名通过，再发请求；攻击者可以让同一域名先解析到公网再切到 `127.0.0.1`。已通过 `validate_redirect_url` 在重定向时复查，但首次请求仍有窗口——需要时在 socket 层做"已解析 IP 校验"。
- **测试需要 allow_private**：localhost 测试时给 `allow_private=True`，但生产代码绝对不能默认开启。
- **新增云提供商元数据 IP**：阿里云 100.100.100.200、腾讯云 169.254.169.254 等需要按需加入 `_METADATA_ENDPOINTS`。
- **IPv6 私网未尽穷举**：当前覆盖 `::1`、`fe80::/10`、`fc00::/7`，但 NAT64 / 6to4 转换地址未列入。

## 修改本机制时的检查清单

- [ ] 添加新工具时第一行调 `validate_url(url, allow_private=False)`
- [ ] 处理 HTTP redirect 时调 `validate_redirect_url`，禁止裸调 httpx 默认 follow_redirects
- [ ] 测试至少覆盖：私网 IP、localhost、metadata 端点、非 http(s) scheme
- [ ] 新增云厂商部署时复查元数据端点列表

## 相关
- 关联条目：[tool-result-envelope](tool-result-envelope.md)
