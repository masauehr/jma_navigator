// 気象庁ナビの画面。表示はすべて textContent で組み立てる（HTMLを文字列で差し込まない）。
(function () {
  "use strict";

  var ALLOWED = ["https://www.jma.go.jp/", "https://www.data.jma.go.jp/"];
  var EXAMPLES = ["明日の那覇の天気", "大雨の見通し", "去年の8月の那覇の気温", "石垣島の今の気温", "津波の情報", "台風の進路"];

  var form = document.getElementById("form");
  var input = document.getElementById("q");
  var result = document.getElementById("result");

  // 気象庁のページ以外へは案内しない
  function isJmaUrl(url) {
    return typeof url === "string" && ALLOWED.some(function (p) { return url.indexOf(p) === 0; });
  }

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  function ask(question, pick) {
    input.value = question;
    result.replaceChildren(el("p", "note", "確認しています…"));
    fetch("/api/guide", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: question, pick: pick || null })
    })
      .then(function (r) { return r.json(); })
      .then(function (data) { render(question, data); })
      .catch(function () {
        result.replaceChildren(el("p", "note", "通信に失敗しました。サーバーが動いているか確認してください。"));
      });
  }

  function render(question, d) {
    var card = el("div", "card");
    if (d.error) {
      card.appendChild(el("p", null, d.error));
    } else if (d.status === "ok" && isJmaUrl(d.url)) {
      renderOk(card, d);
    } else if (d.status === "need_place") {
      renderNeedPlace(card, question, d);
    } else if (d.status === "need_more") {
      card.appendChild(el("h2", null, d.title || "情報が足りません"));
      card.appendChild(el("p", null, "もう少し詳しく入力してください（例: 地名や年月）。"));
    } else {
      card.appendChild(el("h2", null, "該当するページが見つかりませんでした"));
      card.appendChild(el("p", null, "言い方を変えるか、下の「よく使うページ」から探してください。"));
    }
    result.replaceChildren(card);
  }

  function renderOk(card, d) {
    var bosai = d.category === "防災";
    if (bosai) card.className = "card bosai";
    card.appendChild(el("span", bosai ? "tag bosai" : "tag", d.category || ""));
    card.appendChild(el("h2", null, d.title));
    if (d.place) card.appendChild(el("p", null, "対象: " + d.place));
    var a = el("a", "open", "気象庁のページを開く");
    a.href = d.url;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    card.appendChild(a);
    if (bosai) {
      card.appendChild(el("p", "note", "最新の状況は必ず公式ページで確認してください。このアプリは「安全」かどうかを判断しません。"));
    }
    if (d.note) card.appendChild(el("p", "note", d.note));
    if (d.verified !== "confirmed") card.appendChild(el("p", "note", "このページ案内は未確認の項目です。開けない場合はお知らせください。"));
  }

  function renderNeedPlace(card, question, d) {
    card.appendChild(el("h2", null, d.title || "地名を教えてください"));
    var cands = d.candidates || [];
    if (!cands.length) {
      card.appendChild(el("p", null, d.hint || "地名（例: 那覇、東京）を入れてもう一度入力してください。"));
      return;
    }
    card.appendChild(el("p", null, "どの地域ですか？"));
    var box = el("div", "candidates");
    cands.forEach(function (c) {
      var label = c.place + "（" + (c.office_name || c.area || "") + "）";
      var b = el("button", null, label);
      b.type = "button";
      var pick = c.office_code ? { office_code: c.office_code } : { amdno: c.amdno };
      b.addEventListener("click", function () { ask(question, pick); });
      box.appendChild(b);
    });
    card.appendChild(box);
  }

  function renderShortcuts(list) {
    var root = document.getElementById("shortcuts");
    var groups = {};
    list.forEach(function (s) { (groups[s.category] = groups[s.category] || []).push(s); });
    Object.keys(groups).forEach(function (cat) {
      root.appendChild(el("h3", null, cat));
      var ul = el("ul");
      groups[cat].forEach(function (s) {
        if (!isJmaUrl(s.url)) return;
        var li = el("li");
        var a = el("a", null, s.title);
        a.href = s.url;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        li.appendChild(a);
        ul.appendChild(li);
      });
      root.appendChild(ul);
    });
  }

  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    var q = input.value.trim();
    if (q) ask(q);
  });

  var ex = document.getElementById("examples");
  EXAMPLES.forEach(function (t) {
    var b = el("button", null, t);
    b.type = "button";
    b.addEventListener("click", function () { ask(t); });
    ex.appendChild(b);
  });

  fetch("/api/shortcuts").then(function (r) { return r.json(); }).then(renderShortcuts).catch(function () {});
})();
