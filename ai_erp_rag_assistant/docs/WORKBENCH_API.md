# 个人工作台接口设计

`POST /api/workbench/summary` 是 AI 服务对前端暴露的唯一工作台聚合接口。请求使用
`Authorization` 和 `UID` 头透传 ERP 登录态，服务端先调用 `/api/User/userinfo`，再并行读取
布局、待办、审批、消息和今日考勤。页面打开不经过 LLM；只有用户追问时才把该接口已返回的
数据交给模型解释。

## 请求

```json
{
  "user_id": "client-correlation-id",
  "modules": ["layout", "todo", "approvals", "messages", "attendance"],
  "page_size": 5,
  "include_todo_items": false,
  "include_extended_todo_items": false,
  "include_message_items": true,
  "include_cards": false
}
```

前端调用示例（沿用 ERP 登录态，不把 token 放入请求体）：

```javascript
const response = await fetch("/api/workbench/summary", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Authorization": erpAuthorization,
    "UID": String(erpUid),
  },
  body: JSON.stringify({
    user_id: `workbench-${erpUid}`,
    modules: ["layout", "todo", "approvals", "messages", "attendance"],
    page_size: 5,
  }),
});
const workbench = await response.json();
```

首屏只依赖 `counts` 和各模块 `status`；收到 `status: "error"` 时显示模块级重试，
不要把整个页面判定为失败。点击“更多”时重新请求对应模块，并设置明细开关。

`modules` 为空时读取全部 P0 模块。`include_todo_items=true` 返回订单/人员待办摘要；
同时设置 `include_extended_todo_items=true` 才会尝试读取 OA 工单、日志、公告、资产待办
明细（不同 ERP 版本可能只提供其中一个端点）。`include_cards=true` 才会按 ERP 布局读取
`newAddDashboard` 和 `statsDashboard`，且只请求个人布局中明确启用的类型，避免首页无条件
请求客户、财务、库存等重接口。

## 返回

```json
{
  "generated_at": "2026-09-01T02:00:00+00:00",
  "user": {"uid": "8", "name": "张三", "department": "研发部", "avatar": ""},
  "counts": {
    "todo_basic": 3,
    "todo_approval": 2,
    "todo_total": 5,
    "pending_approval": 2,
    "approval_received": 1,
    "unread_message": 12
  },
  "layout": {"status": "ok", "items": [], "count": 0},
  "todo": {"status": "ok", "categories": [], "items": [], "count": 5},
  "approvals": {"status": "ok", "items": [], "total": 141, "counts": {}},
  "messages": {"status": "ok", "groups": {}, "important": [], "count": 12},
  "attendance": {"status": "ok", "today": {}},
  "cards": [],
  "erp_mode": "remote",
  "erp_write_mode": "disabled"
}
```

每个模块有 `ok`、`empty` 或 `error` 状态。一个 ERP 子接口失败时只标记该模块，其他模块仍
可展示；接口不会调用标记已读、打卡、审批通过、保存布局等写操作。

## 现网 ERP 映射

| 工作台模块 | ERP 接口 |
| --- | --- |
| 用户 | `POST /api/User/userinfo` |
| 布局 | `POST /api/workstation/getWorkstationLayout` |
| 待办数量 | `GET /api/todo/count?platform=pc` |
| 待办分类 | `GET /api/todo/typeLists?platform=pc` |
| 待办明细 | `GET /api/todo/lists/orders`、`GET /api/todo/lists/personnel` |
| OA 扩展待办 | `GET /oa/todo/lists/v2`、`GET /oa/todo/lists/pc`、`POST /api/WorkOrder/workorderTodoList` |
| 审批数量 | `POST /api/approval/stateTypeNum` |
| 审批列表 | `POST /api/approvalCenter/overviewList` |
| 消息分组 | `POST /api/message/get-group-counts` |
| 重要消息 | `POST /api/message/get-category-messages` |
| 今日考勤 | `POST /api/workstation/getTodayAttendance` |
| 今日新增卡片 | `POST /api/workstation/newAddDashboard` |
| 统计卡片 | `POST /api/workstation/statsDashboard` |

## 页面建议

工作台采用“先数量、后明细”的渐进加载：首屏调用默认聚合请求，只显示数量卡片和考勤；
用户展开待办或消息时再带上 `include_todo_items=true` / `include_message_items=true`。
审批卡片直接展示前 5 条并以 `total` 标出总量，点击后跳转 ERP 审批中心。扩展待办建议
按分类分组渲染，保留 ERP 返回的 `type`、`title`、`url`、`created_at` 等字段，未知字段
原样透传，避免因 ERP 新增分类导致前端崩溃。

当前已在真实页面观察到的待办分类：工单待办、订单待办、日志待点评、公告待确认、资产确认；
审批分类包括待处理、已处理、抄送我、已发起；消息分类包括审批、采购、考勤、库存、订单、
回款、应付、公告、工单、人事等。分类数量以 ERP 返回值为准，不在 AI 服务侧重新计算。
