"use strict";

globalThis.SpeedtestNodeSelection = (() => {
  function key(value) {
    return String(value ?? "").normalize("NFKC").toLowerCase().replace(/[\s_-]+/g, "");
  }

  function aliases(entries) {
    return new Map(Object.entries(entries).flatMap(([id, names]) => (
      [id, ...names].map((name) => [key(name), id])
    )));
  }

  const cities = aliases({
    shanghai: ["上海", "上海市"],
    beijing: ["北京", "北京市"],
    guangzhou: ["广州", "广州市", "廣州", "廣州市"],
    shenzhen: ["深圳", "深圳市"],
    "hong-kong": ["香港", "香港特别行政区", "香港特別行政區", "Hong Kong SAR"],
    "los-angeles": ["洛杉矶", "洛杉磯"],
  });
  const provinces = aliases({
    shanghai: ["上海", "上海市"],
    beijing: ["北京", "北京市"],
    guangdong: ["广东", "广东省", "廣東", "廣東省", "Guangdong Province"],
  });
  const provinceByCity = new Map([
    ["shanghai", "shanghai"], ["beijing", "beijing"],
    ["guangzhou", "guangdong"], ["shenzhen", "guangdong"],
  ]);
  const carriers = aliases({
    telecom: [
      "电信", "中国电信", "中國電信", "中国电信集团有限公司", "中国电信股份有限公司",
      "China Telecom", "China Telecom Corporation Limited", "China Telecom (Group)",
      "CTCC", "CHN-CT", "CHINANET", "CHINANET-BACKBONE",
      "46003", "46005", "46011", "46012",
    ],
    unicom: [
      "联通", "中国联通", "中國聯通", "中国联合网络通信集团有限公司", "中国联合网络通信有限公司",
      "China Unicom", "China Unicom China169 Backbone", "CUCC", "CHN-UNICOM", "China169-Backbone",
      "46001", "46006", "46009",
    ],
    mobile: [
      "移动", "中国移动", "中國移動", "中国移动通信集团有限公司", "China Mobile", "CMCC",
      "China Mobile Communications Corporation", "China Mobile Communications Group Co., Ltd.",
      "46000", "46002", "46004", "46007", "46008",
    ],
  });

  function normalizeGeo(payload) {
    const data = payload?.data ?? payload;
    const city = cities.get(key(data?.city)) ?? null;
    const province = provinceByCity.get(city)
      ?? provinces.get(key(data?.province ?? data?.region)) ?? null;
    const mcc = String(data?.mcc ?? "").trim();
    const mnc = String(data?.mnc ?? "").trim();
    const plmn = /^\d{3}$/.test(mcc) && /^\d{1,2}$/.test(mnc) ? mcc + mnc.padStart(2, "0") : null;
    const carrier = [data?.plmn, plmn,
      data?.carrier, data?.connection?.isp, data?.isp, data?.asn_organization,
      data?.organization, data?.connection?.org, data?.org]
      .map((value) => carriers.get(key(value))).find(Boolean) ?? null;
    return { city, province, carrier };
  }

  function rank(nodes, { city, province, carrier } = {}) {
    const groups = [
      { reason: "same-city-carrier", nodes: [] },
      { reason: "same-province-carrier", nodes: [] },
      { reason: "same-city", nodes: [] },
      { reason: "mainland-latency", nodes: [] },
    ];
    for (const node of nodes) {
      if (node.verified !== true) continue;
      const sameCity = city && node.city === city;
      const sameCarrier = carrier && node.carrier === carrier;
      const sameProvince = province && node.province === province;
      if (!sameCity && node.mainland !== true) continue;

      if (sameCity && sameCarrier) groups[0].nodes.push(node);
      else if (sameProvince && sameCarrier) groups[1].nodes.push(node);
      else if (sameCity) groups[2].nodes.push(node);
      else groups[3].nodes.push(node);
    }
    return groups.filter((group) => group.nodes.length > 0);
  }

  return { normalizeGeo, rank };
})();
