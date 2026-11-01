"use strict";
(() => {
  const $ = (id) => document.getElementById(id);
  const labels = { quoted: "已报价", funded: "已付款 · 待交付", delivered: "已交付 · 待验收", revision_requested: "需要返工", accepted: "验收通过", rejected: "已拒收 · 已退款", cancelled: "已取消" };
  const actions = { quote: "创建需求 / 报价", fund: "模拟付款", deliver: "卖家交付", review: "买家独立验收", cancel: "取消订单", reset: "新一轮实验" };
  const reasons = { fund: "托管本金", compute: "履约成本", accept: "验收结算", reject_refund: "拒收退款", cancel_refund: "取消退款" };
  const nextSteps = {
    quoted: "检查报价和预算。确认后，服务积分将从买家转入本订单的模拟托管账户。",
    funded: "本金已托管。请选择正常交付或故意注入失败，观察买家是否能发现问题。",
    delivered: "交付不等于成交。请由独立买家检查原始需求与结果；此时不能绕过验收直接取消。",
    revision_requested: "买家发现问题，尚未向卖家结算。可以重新交付，或取消并退回服务本金；已产生的成本不会退回。",
    accepted: "独立验收通过，托管积分已划给卖家。此订单结束，重复请求不会重复结算。",
    rejected: "返工机会已用尽，买家已收回服务本金。卖家承担已消耗的模拟成本。",
    cancelled: "订单已终止，托管中的服务本金已退回。历史成本与操作证据仍保留。"
  };
  const pendingKey = "virtual-trade-lab.pending.v1";
  let state = null;
  let busy = false;
  let pending = null;
  let loadGeneration = 0;
  let connected = false;
  const source = [
    { sku: "CUP-01", title: "  Ceramic   cup  ", price_cents: 1299 },
    { sku: "BAG-02", title: "Canvas\t tote", price_cents: 2499 }
  ];
  $("source").value = JSON.stringify(source, null, 2);

  function node(tag, text, className) {
    const item = document.createElement(tag);
    if (text !== undefined) item.textContent = text;
    if (className) item.className = className;
    return item;
  }

  function notice(message, error = false) {
    $("notice").textContent = message;
    $("notice").className = error ? "notice error" : "notice";
    $("notice").hidden = !message;
  }

  function selectedId() {
    try { return decodeURIComponent(location.hash.slice(1)); } catch { return ""; }
  }

  function selectedOrder() {
    if (!state) return null;
    return state.orders.find((order) => order.id === selectedId()) || state.orders.at(-1) || null;
  }

  function selectOrder(id) {
    if (id && selectedId() !== id) location.hash = encodeURIComponent(id);
    render();
  }

  function formatAccount(account) {
    return { buyer: "买家", seller: "卖家", provider: "成本接收方" }[account] || (account.startsWith("escrow:") ? `订单托管 ${account.slice(7, 15)}` : account);
  }

  function render() {
    const locked = busy || !!pending || !state || !connected;
    $("quote").disabled = locked;
    $("reset").disabled = locked;
    $("refresh").disabled = busy;
    $("retry").disabled = busy || !pending || !state || !connected;
    $("pending-panel").hidden = !pending;
    if (pending) $("pending-description").textContent = `${actions[pending.body.action] || "新一轮实验"} · 请求 ${pending.body.key.slice(0, 8)}`;
    if (!state) return;
    const { balances, initial_total: total } = state;
    $("buyer-balance").textContent = balances.buyer;
    $("seller-balance").textContent = balances.seller;
    $("escrow-balance").textContent = Object.entries(balances).filter(([key]) => key.startsWith("escrow:")).reduce((sum, [, value]) => sum + value, 0);
    const actual = Object.values(balances).reduce((sum, value) => sum + value, 0);
    $("total-balance").textContent = `${actual} = ${total}`;
    $("conservation").textContent = `成本接收方 ${balances.provider} 积分 · ${actual === total ? "账本守恒" : "异常，请停止操作"}`;
    $("version").textContent = `实验 ${state.epoch.slice(0, 8)} / 版本 ${state.revision}`;
    const order = selectedOrder();
    const options = state.orders.map((item, index) => {
      const option = node("option", `订单 ${index + 1} · ${item.id.slice(0, 8)} · ${labels[item.state] || item.state}`);
      option.value = item.id;
      option.selected = order && order.id === item.id;
      return option;
    });
    if (!options.length) {
      const option = node("option", "尚无订单");
      option.value = "";
      options.push(option);
    }
    $("order-select").replaceChildren(...options);
    $("order-select").disabled = !order || busy;
    $("empty-order").hidden = !!order;
    $("order-detail").hidden = !order;
    if (order) {
      $("order-name").textContent = `订单 ${state.orders.findIndex((o) => o.id === order.id) + 1} · ${order.id.slice(0, 8)}`;
      $("order-state").textContent = labels[order.state] || order.state;
      $("order-state").className = `state-pill ${order.state}`;
      const stage = order.state === "quoted" ? 0 : order.state === "funded" ? 1 : ["delivered", "revision_requested"].includes(order.state) ? 2 : 3;
      $("progress").replaceChildren(...["需求 / 报价", "模拟托管", "交付 / 验收", "结算 / 终止"].map((text, index) => node("li", text, index <= stage ? "active" : "")));
      $("order-price").textContent = order.quote.price;
      $("order-cost").textContent = order.cost;
      const net = (order.state === "accepted" ? order.quote.price : 0) - order.cost;
      $("order-net").textContent = `${net >= 0 ? "+" : ""}${net}`;
      $("order-policy").textContent = `预算 ${order.criteria.budget} · 标题上限 ${order.criteria.max_title_length} 字符 · 已交付 ${order.attempts} 次 · 已请求返工 ${order.revisions} / ${order.criteria.max_revisions} 次`;
      $("next-step").textContent = nextSteps[order.state] || "未知状态，请停止操作。";
      $("fund").hidden = order.state !== "quoted";
      $("delivery-controls").hidden = !["funded", "revision_requested"].includes(order.state);
      $("review").hidden = order.state !== "delivered";
      $("cancel").hidden = !["quoted", "funded", "revision_requested"].includes(order.state);
      $("cancel").textContent = order.state === "quoted" ? "取消未付款订单" : "取消订单并退回本金";
      for (const id of ["fund", "deliver", "review", "cancel", "mode"]) $(id).disabled = locked;
      $("issues").hidden = !order.issues.length;
      $("issue-list").replaceChildren(...order.issues.map((text) => node("li", text)));
      $("delivery-output").textContent = order.result === null ? "暂无有效交付。" : JSON.stringify(order.result, null, 2);
      $("source-output").textContent = JSON.stringify(order.source, null, 2);
    }
    $("journal-count").textContent = `${state.journal.length} 笔划转`;
    const eventItems = [...state.events].reverse().map((event) => {
      const li = node("li");
      li.append(node("strong", `#${event.sequence} ${actions[event.action] || event.action} → ${labels[event.state] || event.state}`));
      li.append(node("small", `订单 ${event.order.slice(0, 8)} · 累计成本 ${event.cost_credits} · 交付 ${event.attempts} 次`));
      for (const issue of event.issues || []) li.append(node("small", issue, "event-issue"));
      return li;
    });
    $("event-list").replaceChildren(...(eventItems.length ? eventItems : [node("li", "暂无操作。", "muted-text")]));
    const rows = state.journal.map((entry) => {
      const row = node("tr");
      row.append(node("td", `#${entry.sequence}`), node("td", `${formatAccount(entry.from)} → ${formatAccount(entry.to)}`), node("td", entry.credits), node("td", reasons[entry.reason] || entry.reason));
      return row;
    });
    if (!rows.length) {
      const cell = node("td", "暂无划转。", "muted-text");
      cell.colSpan = 4;
      const row = node("tr");
      row.append(cell);
      rows.push(row);
    }
    $("ledger-body").replaceChildren(...rows);
  }

  async function fetchWithTimeout(url, options = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(url, { ...options, signal: controller.signal });
      // Reading the body is covered by the same deadline as the request.
      const data = await response.json();
      return { response, data };
    } finally {
      clearTimeout(timeout);
    }
  }

  async function readState(quiet = false) {
    const generation = ++loadGeneration;
    try {
      const { response, data } = await fetchWithTimeout("/api/state", { cache: "no-store", credentials: "same-origin" });
      if (!response.ok) throw new Error(data.error || `读取失败 (${response.status})`);
      if (generation !== loadGeneration) return;
      state = data;
      connected = true;
      $("connection").textContent = "● 本地保存已连接 · 刷新 / 重开页面不会重复执行交易";
      if (!quiet && !pending) notice("已读取本地保存。刷新不会执行交易。");
    } catch (error) {
      if (generation !== loadGeneration) return;
      connected = false;
      $("connection").textContent = "● 无法读取本地保存 · 已停止交易操作";
      notice(`读取失败：${error.message}。请检查服务与保存文件；不会自动创建新实验覆盖数据。`, true);
    }
    render();
  }

  function savePending(value) {
    // A request is never sent unless its retry identity is retained for this tab.
    if (value) sessionStorage.setItem(pendingKey, JSON.stringify(value));
    else sessionStorage.removeItem(pendingKey);
    pending = value;
  }

  async function sendPending() {
    if (!pending || busy || !state || !connected) return;
    busy = true;
    ++loadGeneration;
    render();
    const request = pending;
    let refresh = false;
    try {
      const { response, data } = await fetchWithTimeout(request.path, {
        method: "POST", credentials: "same-origin", cache: "no-store",
        headers: { "Content-Type": "application/json", "X-VTL-Token": state.csrf_token },
        body: JSON.stringify(request.body)
      });
      if (!response.ok) {
        if (response.status === 403) {
          // The server may have restarted after committing a request whose response
          // was lost. Preserve its identity while obtaining the new CSRF token.
          refresh = true;
          notice("本次请求被拒绝，连接令牌可能已更新。原请求已保留；将刷新状态，请核对最新流水后点击‘重试同一请求’。", true);
        } else if (response.status >= 400 && response.status < 500) {
          savePending(null);
          refresh = true;
          notice(`本次请求被拒绝：${data.error || response.status}。请核对最新流水；此前结果不确定的请求可能已保存。将读取最新状态，不会自动重试。`, true);
        } else {
          connected = false;
          notice(`服务器未能确认结果：${data.error || response.status}。请求已保留；先刷新恢复连接，再重试同一请求。`, true);
          $("connection").textContent = "● 保存状态待确认 · 交易操作已暂停";
        }
      } else {
        state = data;
        connected = true;
        savePending(null);
        if (request.path === "/api/reset") history.replaceState(null, "", location.pathname + location.search);
        else if (request.body.action === "quote") location.hash = encodeURIComponent(request.body.order_id);
        $("connection").textContent = "● 本地保存已连接 · 最近操作已保存";
        notice(request.path === "/api/reset" ? "新实验已开始。上一轮记录保留在本地存档，不会再次结算。" : `${actions[request.body.action]}已处理并保存。重复相同请求不会重复划转积分。`);
      }
    } catch (error) {
      notice(`请求结果不确定：${error.message}。已保留原请求，请重试同一请求或刷新查看。`, true);
    } finally {
      busy = false;
      render();
      if (refresh) await readState(true);
    }
  }

  function startRequest(path, fields) {
    if (busy || pending || !state || !connected) return;
    try {
      const body = { epoch: state.epoch, expected_revision: state.revision, key: crypto.randomUUID(), ...fields };
      savePending({ path, body });
      sendPending();
    } catch (error) {
      notice(`无法保存请求标识，操作未发送：${error.message}。请允许本地会话存储后重试。`, true);
      render();
    }
  }

  $("quote-form").addEventListener("submit", (event) => {
    event.preventDefault();
    if (!$("quote-form").reportValidity()) return;
    try {
      const parsed = JSON.parse($("source").value);
      if (!Array.isArray(parsed) || !parsed.length) throw new Error("商品目录必须是非空 JSON 数组");
      const criteria = { budget: Number($("budget").value), max_revisions: Number($("revisions").value), max_title_length: Number($("title-length").value) };
      if (!Object.values(criteria).every(Number.isSafeInteger)) throw new Error("验收参数必须是整数");
      startRequest("/api/command", { action: "quote", order_id: crypto.randomUUID(), payload: { source: parsed, criteria } });
    } catch (error) { notice(`输入有误：${error.message}`, true); }
  });
  for (const action of ["fund", "deliver", "review", "cancel"]) {
    $(action).addEventListener("click", () => {
      const order = selectedOrder();
      if (order) startRequest("/api/command", { action, order_id: order.id, payload: action === "deliver" ? { mode: $("mode").value } : {} });
    });
  }
  $("refresh").addEventListener("click", () => readState());
  $("retry").addEventListener("click", sendPending);
  $("order-select").addEventListener("change", (event) => selectOrder(event.target.value));
  $("reset").addEventListener("click", () => { if (!busy && !pending && state && connected) $("reset-dialog").showModal(); });
  $("reset-confirm").addEventListener("click", () => {
    $("reset-dialog").close();
    startRequest("/api/reset", {});
  });
  window.addEventListener("hashchange", render);
  window.addEventListener("pageshow", () => { if (!busy) readState(true); });
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible" && !busy) readState(true); });
  try {
    const saved = sessionStorage.getItem(pendingKey);
    if (saved) {
      const item = JSON.parse(saved);
      if (!["/api/command", "/api/reset"].includes(item.path) || !item.body || typeof item.body.key !== "string" || typeof item.body.epoch !== "string") throw new Error("旧请求格式无效");
      pending = item;
    }
  } catch (error) {
    notice(`无法恢复上次请求：${error.message}。未自动发送任何操作。`, true);
  }
  render();
  readState(true);
})();
