"use strict";

const preview = document.documentElement.dataset.mode !== "live";
const historyKey = "u30-speedtest:history:v1";
const unitKey = "u30-speedtest:unit:v1";
const languageKey = "u30-speedtest:language:v1";
const locationKey = "u30-speedtest:location:v1";
const historyLimit = 10;
const tiers = [10, 20, 50, 100, 200, 300, 500, 1000, 2000];
const provinces = { shanghai: "shanghai", beijing: "beijing", guangzhou: "guangdong", shenzhen: "guangdong" };
const carriers = ["telecom", "unicom", "mobile"];
const nodes = [
  {
    id: "mfcyun", name: "mfcyunName",
    province: "guangdong", carrier: "mobile", mainland: true, verified: true,
    settings: {
      url_dl: "https://speedtest.mfcyun.com/backend/garbage.php?cors=true",
      url_ul: "https://speedtest.mfcyun.com/backend/empty.php?cors=true",
      url_ping: "https://speedtest.mfcyun.com/backend/empty.php?cors=true",
      garbagePhp_chunkSize: 4,
    },
  },
  {
    id: "shanghai", name: "shanghaiName",
    city: "shanghai", province: "shanghai", carrier: "telecom", mainland: true, verified: true,
    settings: {
      url_dl: "https://speedtest1.online.sh.cn:8080/download?nocache=1&size=10485760",
      url_ul: "https://speedtest1.online.sh.cn:8080/upload?nocache=1",
      url_ping: "https://speedtest1.online.sh.cn:8080/hi?nocache=1",
    },
  },
  {
    id: "hong-kong", name: "hkName",
    city: "hong-kong", verified: true,
    settings: {
      url_dl: "https://www.speedtest.hk/speedtest/download.php?bytes=10485760",
      url_ul: "https://www.speedtest.hk/speedtest/upload.php",
      url_ping: "https://www.speedtest.hk/speedtest/ping.php",
    },
  },
  {
    id: "los-angeles", name: "losAngelesName",
    city: "los-angeles", verified: true,
    settings: {
      url_dl: "https://la.speedtest.clouvider.net/backend/garbage.php?cors=true",
      url_ul: "https://la.speedtest.clouvider.net/backend/empty.php?cors=true",
      url_ping: "https://la.speedtest.clouvider.net/backend/empty.php?cors=true",
      garbagePhp_chunkSize: 4,
    },
  },
];

const copy = {
  zh: {
    brand: "网络测试",
    languageLabel: "语言", nodeLabel: "指定服务器", unitLabel: "速率单位",
    connectionLabel: "当前网络", ipLabel: "公网 IP", currentCarrierLabel: "蜂窝运营商",
    serverLabel: "测速服务器",
    detecting: "正在识别…", unknown: "暂未识别",
    choosingServer: "正在匹配服务器…", noServer: "暂无可用服务器", manualServer: "手动指定",
    noServerDetail: "可更改选点设置，或点击开始测速重试。",
    cityLabel: "所在城市", carrierLabel: "运营商",
    automaticNode: "按城市和运营商匹配", automaticCity: "自动识别城市", automaticCarrier: "自动识别运营商",
    cities: { shanghai: "上海", beijing: "北京", guangzhou: "广州", shenzhen: "深圳", guangdong: "广东（省级）", "hong-kong": "中国香港", "los-angeles": "美国洛杉矶" },
    carriers: { telecom: "中国电信", unicom: "中国联通", mobile: "中国移动" },
    matchReasons: { "same-city-carrier": "同城同运营商", "same-province-carrier": "同省同运营商", "same-city": "同城可用节点", "mainland-latency": "国内可用节点中响应最快" },
    carrierFallback: (city, carrier, reason) => `暂无${[city, carrier].filter(Boolean).join(" ")}节点 · ${reason}`,
    choosing: "正在选择测速节点", noReachableNode: "没有可用的自动测速节点，请手动切换或重试。",
    resultsTitle: "测速结果", download: "下载", upload: "上传", ping: "Ping 延迟",
    equivalentLabel: "等效宽带", equivalentPrefix: "约", equivalentSuffix: "宽带",
    uploadEquivalent: "上传等效",
    publicEstimate: "按公网实测速率估算。",
    historyTitle: "最近 10 次测速", historyLabel: "测速历史", time: "时间", node: "节点",
    historyEmpty: "完成第一次测速后，结果会显示在这里。", historyCount: (count) => `已记录 ${count} 次`,
    demo: "演示数据", localName: "U30 Air · 本地", hkName: "Speedtest.hk · 中国香港",
    shanghaiName: "上海电信 · 上海", mfcyunName: "梦飞云 · 广东移动",
    losAngelesName: "Clouvider · 美国洛杉矶",
    start: "开始测速", stop: "停止测速", ready: "准备就绪", connecting: "正在连接测速节点",
    testingPing: "正在测量延迟", testingDownload: "正在测量下载速度", testingUpload: "正在测量上传速度",
    complete: "测速完成", demoComplete: "演示完成", unsaved: "测速完成。此浏览器无法保存历史。",
    canceled: "已停止测速。", incomplete: "本次未取得完整结果，请检查网络或切换节点。",
    unavailable: "测速模块未启动，请刷新页面后重试。",
    tier: (value) => `${value}M`, lowTier: "低于 10M", highTier: "2000M+",
  },
  en: {
    brand: "Network Test",
    languageLabel: "Language", nodeLabel: "Specific server", unitLabel: "Speed unit",
    connectionLabel: "Current network", ipLabel: "Public IP", currentCarrierLabel: "Cellular carrier",
    serverLabel: "Test server",
    detecting: "Detecting…", unknown: "Unavailable",
    choosingServer: "Finding a server…", noServer: "No server available", manualServer: "Manually selected",
    noServerDetail: "Change the server settings or start a test to try again.",
    cityLabel: "Your city", carrierLabel: "Carrier",
    automaticNode: "Match by city and carrier", automaticCity: "Detect city", automaticCarrier: "Detect carrier",
    cities: { shanghai: "Shanghai", beijing: "Beijing", guangzhou: "Guangzhou", shenzhen: "Shenzhen", guangdong: "Guangdong (province)", "hong-kong": "Hong Kong, China", "los-angeles": "Los Angeles, US" },
    carriers: { telecom: "China Telecom", unicom: "China Unicom", mobile: "China Mobile" },
    matchReasons: { "same-city-carrier": "Same city and carrier", "same-province-carrier": "Same province and carrier", "same-city": "Available server in the same city", "mainland-latency": "Fastest response among mainland servers" },
    carrierFallback: (city, carrier, reason) => `No ${carrier} server${city ? ` in ${city}` : ""} · ${reason}`,
    choosing: "Choosing a test server", noReachableNode: "No automatic server is reachable. Choose a server manually or retry.",
    resultsTitle: "Test results", download: "Download", upload: "Upload", ping: "Ping latency",
    equivalentLabel: "Equivalent broadband", equivalentPrefix: "About", equivalentSuffix: "broadband",
    uploadEquivalent: "Upload equivalent",
    publicEstimate: "Estimated from your internet measurements.",
    historyTitle: "Last 10 tests", historyLabel: "Test history", time: "Time", node: "Server",
    historyEmpty: "Your first result will appear here after the test.", historyCount: (count) => `${count} saved ${count === 1 ? "test" : "tests"}`,
    demo: "Sample data", localName: "U30 Air · Local", hkName: "Speedtest.hk · Hong Kong, China",
    shanghaiName: "China Telecom · Shanghai", mfcyunName: "MFCYun · Guangdong Mobile",
    losAngelesName: "Clouvider · Los Angeles, US",
    start: "Start test", stop: "Stop test", ready: "Ready", connecting: "Connecting to test server",
    testingPing: "Measuring latency", testingDownload: "Measuring download speed", testingUpload: "Measuring upload speed",
    complete: "Test complete", demoComplete: "Demo complete", unsaved: "Test complete. This browser could not save the result.",
    canceled: "Test stopped.", incomplete: "The test did not finish. Check your connection or choose another server.",
    unavailable: "The test engine could not start. Refresh the page and try again.",
    tier: (value) => `${value} Mbps`, lowTier: "Under 10 Mbps", highTier: "2000+ Mbps",
  },
};

const byId = (id) => document.getElementById(id);
const nodeSelect = byId("node-select");
const citySelect = byId("city-select");
const carrierSelect = byId("carrier-select");
const serverSettings = byId("server-settings");
const startButton = byId("start-test");
const status = byId("test-status");
const languageSelect = byId("language-select");
const unitButtons = [...byId("unit-select").querySelectorAll("[data-unit]")];
const samples = {
  shanghai: { download: 478.40, upload: 48.32, ping: 21.56 },
  mfcyun: { download: 256.40, upload: 38.16, ping: 29.18 },
  "hong-kong": { download: 285.64, upload: 42.68, ping: 31.22 },
  "los-angeles": { download: 84.72, upload: 15.36, ping: 171.45 },
};
const examples = [
  { ...samples.mfcyun, node: "mfcyun", time: Date.now() - 240000 },
  { ...samples.shanghai, node: "shanghai", time: Date.now() - 7200000 },
  { ...samples["hong-kong"], node: "hong-kong", time: Date.now() - 86400000 },
];

function readStorage(key) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key, value) {
  try {
    localStorage.setItem(key, value);
    return true;
  } catch {
    return false;
  }
}

function isResult(result) {
  return result && (result.node === "local" || nodes.some((node) => node.id === result.node))
    && Number.isFinite(result.time) && Number.isFinite(new Date(result.time).valueOf())
    && Number.isFinite(result.download) && result.download > 0
    && Number.isFinite(result.upload) && result.upload > 0
    && Number.isFinite(result.ping) && result.ping >= 0;
}

function readHistory() {
  if (preview) return examples;
  try {
    const records = JSON.parse(readStorage(historyKey));
    return Array.isArray(records) ? records.filter(isResult).slice(0, historyLimit) : [];
  } catch {
    return [];
  }
}

let history = readHistory();
let unit = !preview && readStorage(unitKey) === "Mbps" ? "Mbps" : "MB/s";
const savedLanguage = readStorage(languageKey);
let language = savedLanguage === "zh" || savedLanguage === "en" ? savedLanguage
  : /^zh\b/i.test(navigator.languages?.[0] || navigator.language || "zh") ? "zh" : "en";
let result;
let activeTest = null;
let recommendation = null;
let selectionTask = null;
let connection = null;
let connectionLookup;
let statusKey = "ready";
let dateFormat;

function setStatus(key) {
  statusKey = key;
  const text = copy[language][key];
  if (status.textContent !== text) status.textContent = text;
}

function formatSpeed(mbps) {
  if (!Number.isFinite(mbps)) return "";
  return (unit === "MB/s" ? mbps / 8 : mbps).toFixed(2);
}

function formatPing(ms) {
  return Number.isFinite(ms) ? String(Math.round(ms)) : "";
}

function estimateTier(mbps) {
  if (!Number.isFinite(mbps)) return "";
  if (mbps < tiers[0] / 2) return copy[language].lowTier;
  if (mbps > tiers[tiers.length - 1]) return copy[language].highTier;
  const nearest = tiers.reduce((best, tier) => (
    Math.abs(tier - mbps) < Math.abs(best - mbps) ? tier : best
  ));
  return copy[language].tier(nearest);
}

function renderReading(id, text) {
  const value = byId(id);
  value.textContent = text;
  value.parentElement.hidden = text === "";
}

function renderGauge(direction, mbps) {
  renderReading(`${direction}-value`, formatSpeed(mbps));
  // Use the reference meter's scale so low and high speeds remain legible on the same arc.
  const fill = Number.isFinite(mbps) && mbps > 0
    ? 100 * (1 - 1 / Math.pow(1.3, Math.sqrt(mbps))) : 0;
  byId(`${direction}-gauge`).setAttribute("stroke-dasharray", `${fill} 100`);
}

function renderResult() {
  renderReading("ping-value", formatPing(result?.ping));
  renderGauge("download", result?.download);
  renderGauge("upload", result?.upload);
  const completed = Number.isFinite(result?.time);
  byId("plan-main").hidden = !completed;
  byId("plan-detail").hidden = !completed;
  byId("plan-download").textContent = estimateTier(completed ? result.download : undefined);
  byId("plan-upload").textContent = estimateTier(completed ? result.upload : undefined);
}

function renderHistory() {
  const strings = copy[language];
  const labels = [strings.time, strings.node, strings.ping, strings.download, strings.upload, strings.equivalentLabel];
  byId("history-body").replaceChildren(...history.map((entry) => {
    const row = document.createElement("tr");
    row.setAttribute("role", "row");
    const node = nodes.find((item) => item.id === entry.node);
    const values = [dateFormat.format(entry.time), strings[node?.name ?? "localName"], `${formatPing(entry.ping)} ms`,
      `${formatSpeed(entry.download)} ${unit}`, `${formatSpeed(entry.upload)} ${unit}`,
      estimateTier(entry.download)];
    values.forEach((value, index) => {
      const cell = row.insertCell();
      cell.setAttribute("role", "cell");
      cell.dataset.label = labels[index];
      cell.textContent = value;
    });
    return row;
  }));
  byId("history-empty").hidden = history.length > 0;
  const count = byId("history-count");
  count.textContent = `${history.length} / ${historyLimit}`;
  count.setAttribute("aria-label", strings.historyCount(history.length));
}

function renderUnits() {
  for (const button of unitButtons) {
    button.setAttribute("aria-pressed", String(button.dataset.unit === unit));
  }
  for (const label of document.querySelectorAll(".speed-unit")) label.textContent = unit;
  renderResult();
  renderHistory();
}

function renderConnection() {
  const strings = copy[language];
  byId("connection-ip").textContent = connection ? connection.ip || strings.unknown : strings.detecting;
  byId("connection-carrier").textContent = connection
    ? strings.carriers[connection.registeredCarrier] || strings.unknown : strings.detecting;
}

function renderServer() {
  const strings = copy[language];
  byId("server-name").textContent = recommendation ? strings[recommendation.node.name]
    : selectionTask ? strings.choosingServer : strings.noServer;
  let description = selectionTask ? "" : strings.noServerDetail;
  if (recommendation) {
    const { node, reason, city, carrier } = recommendation;
    description = strings.matchReasons[reason] || strings.manualServer;
    if (carrier && node.carrier !== carrier
        && (city || !nodes.some((entry) => entry.verified && entry.mainland && entry.carrier === carrier))) {
      description = strings.carrierFallback(strings.cities[city], strings.carriers[carrier], description);
    }
  }
  byId("server-description").textContent = description;
}

function renderSelectors(strings) {
  const selectedNode = nodeSelect.value;
  const selectedCity = citySelect.value;
  const selectedCarrier = carrierSelect.value;
  nodeSelect.replaceChildren(new Option(strings.automaticNode, ""));
  const groups = new Map();
  for (const node of nodes) {
    const region = node.city || node.province;
    if (!groups.has(region)) {
      const group = document.createElement("optgroup");
      group.label = strings.cities[region];
      groups.set(region, group);
      nodeSelect.append(group);
    }
    groups.get(region).append(new Option(strings[node.name], node.id));
  }
  nodeSelect.value = selectedNode;
  citySelect.replaceChildren(new Option(strings.automaticCity, ""),
    ...Object.keys(provinces).map((id) => new Option(strings.cities[id], id)));
  carrierSelect.replaceChildren(new Option(strings.automaticCarrier, ""),
    ...carriers.map((id) => new Option(strings.carriers[id], id)));
  citySelect.value = selectedCity;
  carrierSelect.value = selectedCarrier;
}

function renderLanguage() {
  const strings = copy[language];
  const locale = language === "zh" ? "zh-CN" : "en";
  document.documentElement.lang = locale;
  document.title = strings.brand;
  dateFormat = new Intl.DateTimeFormat(locale, {
    month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  });
  languageSelect.value = language;
  for (const label of document.querySelectorAll("[data-i18n]")) label.textContent = strings[label.dataset.i18n];
  for (const label of document.querySelectorAll("[data-i18n-label]")) {
    label.setAttribute("aria-label", strings[label.dataset.i18nLabel]);
  }
  renderSelectors(strings);
  const demoBadge = byId("mode-badge");
  demoBadge.hidden = !preview;
  demoBadge.textContent = strings.demo;
  startButton.textContent = strings[activeTest ? "stop" : "start"];
  setStatus(statusKey);
  renderConnection();
  renderServer();
  byId("plan-detail").textContent = strings.publicEstimate;
  renderUnits();
}

async function fetchWithTimeout(url, signal, read) {
  if (signal.aborted) return null;
  const controller = new AbortController();
  const abort = () => controller.abort();
  const timeout = setTimeout(abort, 2200);
  signal.addEventListener("abort", abort, { once: true });
  try {
    const response = await fetch(url, {
      signal: controller.signal, cache: "no-store", credentials: "omit", referrerPolicy: "no-referrer",
    });
    return response.ok ? await read(response) : null;
  } catch {
    return null;
  } finally {
    clearTimeout(timeout);
    signal.removeEventListener("abort", abort);
  }
}

let carrierRequest = 0;
function queryRegisteredCarrier(signal) {
  if (window.parent === window || signal.aborted) return Promise.resolve(null);
  return new Promise((resolve) => {
    const requestId = String(++carrierRequest);
    const finish = (plmn) => {
      clearTimeout(timeout);
      window.removeEventListener("message", onMessage);
      signal.removeEventListener("abort", abort);
      resolve(plmn);
    };
    const abort = () => finish(null);
    const onMessage = (event) => {
      const message = event.data;
      if (event.origin === window.location.origin && event.source === window.parent
          && message?.type === "mu300-speedtest:carrier-response" && message.requestId === requestId) {
        finish(typeof message.plmn === "string" && /^\d{5,6}$/.test(message.plmn) ? message.plmn : null);
      }
    };
    const timeout = setTimeout(abort, 5000);
    signal.addEventListener("abort", abort, { once: true });
    window.addEventListener("message", onMessage);
    window.parent.postMessage({ type: "mu300-speedtest:carrier-request", requestId }, window.location.origin);
  });
}

async function detectConnection() {
  const { normalizeGeo } = window.SpeedtestNodeSelection;
  const signal = new AbortController().signal;
  const [location, plmn] = preview
    ? [{ ip: "192.0.2.42", city: "Shanghai", isp: "China Telecom" }, null]
    : await Promise.all([
      fetchWithTimeout("https://api.ip.sb/geoip", signal, (response) => response.json()),
      queryRegisteredCarrier(signal),
    ]);
  const ip = typeof location?.ip === "string" && /^[0-9a-f:.]{2,45}$/i.test(location.ip) ? location.ip : "";
  connection = { ip, geo: normalizeGeo(location), registeredCarrier: normalizeGeo({ plmn }).carrier };
  renderConnection();
  return connection;
}

async function selectAutomaticNode({ geo, registeredCarrier }, signal) {
  const selectedCity = citySelect.value;
  const selectedCarrier = carrierSelect.value;
  const { rank } = window.SpeedtestNodeSelection;
  const city = selectedCity || (Object.hasOwn(provinces, geo.city) ? geo.city : null);
  const province = provinces[city] || geo.province;
  const carrier = selectedCarrier || registeredCarrier || geo.carrier;
  for (const group of rank(nodes, { city, province, carrier })) {
    if (signal.aborted) return null;
    if (preview) return { node: group.nodes[0], reason: group.reason, city, carrier };
    const probes = await Promise.all(group.nodes.map(async (node) => {
      const url = new URL(node.settings.url_ping);
      url.searchParams.set("r", String(Date.now()));
      const started = performance.now();
      const latency = await fetchWithTimeout(url, signal, () => performance.now() - started);
      return { node, latency };
    }));
    const fastest = probes.filter(({ latency }) => latency !== null).sort((a, b) => a.latency - b.latency)[0];
    if (fastest && !signal.aborted) return { node: fastest.node, reason: group.reason, city, carrier };
  }
  return null;
}

function refreshRecommendation() {
  selectionTask?.controller.abort();
  const manualNode = nodes.find((node) => node.id === nodeSelect.value);
  if (manualNode) {
    selectionTask = null;
    recommendation = { node: manualNode };
    renderServer();
    return Promise.resolve(recommendation);
  }
  const task = { controller: new AbortController() };
  selectionTask = task;
  recommendation = null;
  renderServer();
  task.promise = connectionLookup
    .then((network) => selectAutomaticNode(network, task.controller.signal))
    .catch(() => null)
    .then((match) => {
      if (selectionTask === task) {
        selectionTask = null;
        recommendation = match;
        renderServer();
      }
      return match;
    });
  return task.promise;
}

function runPreview(node, update, complete) {
  const demo = samples[node.id];
  let step = 0;
  const interval = setInterval(() => {
    step += 1;
    update({
      download: step > 2 ? demo.download * Math.min(1, (step - 2) / 4) : undefined,
      upload: step > 6 ? demo.upload * Math.min(1, (step - 6) / 4) : undefined,
      ping: demo.ping,
    }, step < 3 ? "testingPing" : step < 7 ? "testingDownload" : "testingUpload");
    if (step === 10) {
      clearInterval(interval);
      complete(demo);
    }
  }, 180);
  return () => clearInterval(interval);
}

function runLive(node, update, complete) {
  const engine = new window.Speedtest();
  engine.setParameter("telemetry_level", 0);
  engine.setParameter("test_order", "P_D_U");
  engine.setParameter("xhr_ignoreErrors", 0);
  engine.setParameter("time_dl_max", 10);
  engine.setParameter("time_ul_max", 10);
  engine.setParameter("time_auto", false);
  engine.setParameter("xhr_dlMultistream", 3);
  engine.setParameter("xhr_ulMultistream", 3);
  for (const [key, value] of Object.entries(node.settings)) engine.setParameter(key, value);
  let latest;
  let timer;
  function stopWorker() {
    clearTimeout(timer);
    clearInterval(engine.updater);
    engine.worker?.terminate();
  }
  function measuredValue(status) {
    const value = Number.parseFloat(status);
    return Number.isFinite(value) && value > 0 ? value : undefined;
  }
  engine.onupdate = (data) => {
    latest = {
      download: measuredValue(data.dlStatus),
      upload: measuredValue(data.ulStatus),
      ping: measuredValue(data.pingStatus),
    };
    const label = { 1: "testingDownload", 2: "testingPing", 3: "testingUpload" }[data.testState] || "connecting";
    update(latest, label);
  };
  engine.onend = (aborted) => {
    stopWorker();
    complete(aborted ? undefined : latest);
  };
  engine.start();
  engine.worker.onerror = () => {
    stopWorker();
    complete();
  };
  timer = setTimeout(engine.worker.onerror, 55000);
  return stopWorker;
}

function setTestControls(running) {
  for (const select of [nodeSelect, citySelect, carrierSelect]) select.disabled = running;
  startButton.textContent = copy[language][running ? "stop" : "start"];
  if (running) startButton.setAttribute("aria-busy", "true");
  else startButton.removeAttribute("aria-busy");
}

function finishTest(job, values, failure) {
  if (activeTest !== job) return;
  activeTest = null;
  setTestControls(false);
  const completed = job.node && values && { ...values, node: job.node.id, time: Date.now() };
  if (isResult(completed)) {
    result = completed;
    history = [completed, ...history].slice(0, historyLimit);
    const saved = preview || writeStorage(historyKey, JSON.stringify(history));
    setStatus(preview ? "demoComplete" : saved ? "complete" : "unsaved");
    renderHistory();
  } else {
    if (failure === "canceled") result = job.previousResult;
    setStatus(failure || "incomplete");
  }
  renderResult();
}

startButton.addEventListener("click", async () => {
  if (activeTest) {
    const job = activeTest;
    job.stop?.();
    finishTest(job, undefined, "canceled");
    return;
  }
  const job = {
    node: recommendation?.node,
    previousResult: result,
  };
  activeTest = job;
  result = undefined;
  serverSettings.open = false;
  renderResult();
  setTestControls(true);
  try {
    if (!job.node) {
      setStatus("choosing");
      const selected = await (selectionTask?.promise || refreshRecommendation());
      if (activeTest !== job) return;
      if (!selected) {
        finishTest(job, undefined, "noReachableNode");
        return;
      }
      job.node = selected.node;
    }
    setStatus("connecting");
    const update = (values, label) => {
      if (activeTest !== job) return;
      result = values;
      renderResult();
      setStatus(label);
    };
    const complete = (values) => finishTest(job, values);
    job.stop = preview ? runPreview(job.node, update, complete) : runLive(job.node, update, complete);
  } catch {
    finishTest(job, undefined, "unavailable");
  }
});

for (const button of unitButtons) {
  button.addEventListener("click", () => {
    unit = button.dataset.unit;
    if (!preview) writeStorage(unitKey, unit);
    renderUnits();
  });
}

languageSelect.addEventListener("change", () => {
  language = languageSelect.value;
  writeStorage(languageKey, language);
  renderLanguage();
});
renderLanguage();
try {
  const saved = JSON.parse(readStorage(locationKey));
  if (Object.hasOwn(provinces, saved?.city)) citySelect.value = saved.city;
  if (carriers.includes(saved?.carrier)) carrierSelect.value = saved.carrier;
} catch {
  // Ignore invalid or unavailable preferences.
}
for (const select of [citySelect, carrierSelect]) {
  select.addEventListener("change", () => {
    nodeSelect.value = "";
    if (!preview) writeStorage(locationKey, JSON.stringify({ city: citySelect.value, carrier: carrierSelect.value }));
    result = undefined;
    setStatus("ready");
    renderResult();
    refreshRecommendation();
  });
}
nodeSelect.addEventListener("change", () => {
  result = history.find((entry) => entry.node === nodeSelect.value);
  setStatus("ready");
  renderResult();
  refreshRecommendation();
});
connectionLookup = detectConnection();
refreshRecommendation();
