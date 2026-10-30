// 気象庁ナビの画面。表示はすべて textContent で組み立てる（HTMLを文字列で差し込まない）。
(function () {
  "use strict";

  var ALLOWED = ["https://www.jma.go.jp/", "https://www.data.jma.go.jp/"];
  var EXAMPLES = ["明日の那覇の天気", "大雨の見通し", "去年の8月の那覇の気温", "石垣島の今の気温", "津波の情報", "台風の進路"];

  var form = document.getElementById("form");
  var input = document.getElementById("q");
  var result = document.getElementById("result");

  // 「違う」のあとの絞り込み状態。サーバーは何も覚えず、毎回この内容を送る
  var state = { refine: {}, exclude: [], scope: null };

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

  function link(cls, text, url) {
    var a = el("a", cls, text);
    a.href = url;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    return a;
  }

  // 新しい質問のときは絞り込みをリセットする
  function newQuestion(question) {
    state = { refine: {}, exclude: [], scope: null };
    ask(question);
  }

  function ask(question, pick) {
    input.value = question;
    result.replaceChildren(el("p", "note", "確認しています…"));
    fetch("/api/guide", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: question, pick: pick || null, refine: state.refine, exclude: state.exclude, scope: state.scope })
    })
      .then(function (r) { return r.json(); })
      .then(function (data) { render(question, data); })
      .catch(function () {
        result.replaceChildren(el("p", "note", "通信に失敗しました。サーバーが動いているか確認してください。"));
      });
  }

  function render(question, d) {
    var frag = document.createDocumentFragment();
    var card = el("div", "card");
    frag.appendChild(card);
    if (d.error) {
      card.appendChild(el("p", null, d.error));
    } else if (d.status === "ok" && isJmaUrl(d.url)) {
      renderOk(card, d);
      if (d.comment) frag.appendChild(commentBox(d.comment));
      frag.appendChild(feedback(question, d));
    } else if (d.status === "need_place") {
      renderNeedPlace(card, question, d);
    } else if (d.status === "choose") {
      card.appendChild(el("h2", null, "どれに近いですか？"));
      card.appendChild(el("p", null, "質問だけでは1つに決められませんでした。近いページを選ぶか、下の絞り込みを使ってください。"));
      frag.appendChild(refinePanel(question, d.choices, "絞り込み"));
    } else if (d.status === "need_more") {
      card.appendChild(el("h2", null, d.title || "情報が足りません"));
      card.appendChild(el("p", null, "もう少し詳しく入力してください（例: 地名や年月）。"));
    } else {
      card.appendChild(el("h2", null, "該当するページが見つかりませんでした"));
      card.appendChild(el("p", null, "言い方を変えるか、次から選んでください。"));
      if (d.choices) frag.appendChild(refinePanel(question, d.choices, "絞り込み"));
    }
    var alts = alternativesBox(d.alternatives);
    if (alts) frag.appendChild(alts);
    result.replaceChildren(frag);
  }

  function renderOk(card, d) {
    var bosai = d.category === "防災";
    if (bosai) card.className = "card bosai";
    card.appendChild(el("span", bosai ? "tag bosai" : "tag", d.category || ""));
    card.appendChild(el("h2", null, d.title));
    if (d.place) card.appendChild(el("p", null, "対象: " + d.place));
    if (d.reason) card.appendChild(el("p", "note", "選んだ理由: " + d.reason));
    card.appendChild(link("open", "気象庁のページを開く", d.url));
    var sc = scopeRow(d);
    if (sc) card.appendChild(sc);
    if (bosai) {
      card.appendChild(el("p", "note", "最新の状況は必ず公式ページで確認してください。このアプリは「安全」かどうかを判断しません。"));
    }
    if (d.note) card.appendChild(el("p", "note", d.note));
    if (d.verified !== "confirmed") card.appendChild(el("p", "note", "このページ案内は未確認の項目です。開けない場合はお知らせください。"));
  }

  function renderNeedPlace(card, question, d) {
    card.appendChild(el("h2", null, d.title || "地名を教えてください"));
    var cands = d.candidates || [];
    var sc = scopeRow(d, question);
    if (!cands.length) {
      card.appendChild(el("p", null, d.hint || "地名（例: 那覇、東京）を入れてもう一度入力してください。"));
      if (sc) card.appendChild(sc);
      return;
    }
    card.appendChild(el("p", null, d.scope === "class20s" ? "どの市町村ですか？" : d.scope === "centers" ? "どの地方ですか？" : "どの地域ですか？"));
    var box = el("div", "candidates");
    cands.forEach(function (c) {
      var sub = c.station_code ? (c.area || "") : (c.office_name || c.area || "");
      var label = sub ? c.place + "（" + sub + "）" : c.place;
      var b = el("button", null, label);
      b.type = "button";
      var pick = c.center_code ? { center_code: c.center_code }
        : c.station_code ? { station_code: c.station_code }
        : c.class20_code ? { office_code: c.office_code, class20_code: c.class20_code }
        : c.office_code ? { office_code: c.office_code } : { amdno: c.amdno };
      b.addEventListener("click", function () { ask(question, pick); });
      box.appendChild(b);
    });
    card.appendChild(box);
    if (sc) card.appendChild(sc);
  }

  // 地域の単位（全国・府県・市町村）。警報・注意報は市町村ごとに発表されるため、単位を選べるようにする
  function scopeRow(d, question) {
    if (!d.scopes || d.scopes.length < 2) return null;
    var q = question || input.value.trim();
    var row = el("div", "scope");
    row.appendChild(el("span", "note", "地域の単位:"));
    d.scopes.forEach(function (s) {
      var b = el("button", s.value === d.scope ? "on" : null, s.label);
      b.type = "button";
      b.addEventListener("click", function () { state.scope = s.value; ask(q); });
      row.appendChild(b);
    });
    return row;
  }

  // 気象台からのコメント（予報官の文章を要約せず、そのまま）。発表日時と出典を必ず付ける
  function commentBox(c) {
    var box = el("div", "card comment");
    box.appendChild(el("h2", null, "気象台からのコメント" + (c.office_name ? "（" + c.office_name + "）" : "")));
    if (c.unavailable) {
      box.appendChild(el("p", null, "コメントを取得できませんでした。上の「気象庁のページを開く」で確認してください。"));
      return box;
    }
    box.appendChild(el("p", "note", "発表: " + (c.published || "不明")));
    if (c.stale) {
      box.appendChild(el("p", "warn", "発表から時間が経っている可能性があります。最新の内容は気象庁のページで確認してください。"));
    }
    box.appendChild(el("pre", "comment-text", c.text));
    box.appendChild(el("p", "note", "出典: 気象庁「気象台からのコメント」の文章をそのまま表示しています（このアプリが書いたものではありません）。"));
    return box;
  }

  // 次点以下の候補。リンクが開けるものはリンク、地域が必要なものは説明だけ出す
  function alternativesBox(alts) {
    if (!alts || !alts.length) return null;
    var box = el("div", "card alts");
    box.appendChild(el("h2", null, "他に考えられるページ"));
    var ul = el("ul");
    alts.forEach(function (a) {
      var li = el("li");
      if (a.status === "ok" && isJmaUrl(a.url)) {
        li.appendChild(link(null, a.title, a.url));
        if (a.place) li.appendChild(el("span", "place", "（" + a.place + "）"));
      } else {
        li.appendChild(el("span", "plain", a.title));
        li.appendChild(el("span", "place", "（地域名を入れると開けます）"));
      }
      if (a.reason) li.appendChild(el("div", "note", a.reason));
      ul.appendChild(li);
    });
    box.appendChild(ul);
    return box;
  }

  // 「このページで合っていましたか？」。回答は保存せず、絞り込みの入口にだけ使う
  function feedback(question, d) {
    var box = el("div", "feedback");
    box.appendChild(el("span", null, "このページで合っていましたか？"));
    var yes = el("button", null, "はい");
    var no = el("button", null, "違う");
    yes.type = no.type = "button";
    yes.addEventListener("click", function () {
      box.replaceChildren(el("span", null, "ありがとうございます。"));
    });
    no.addEventListener("click", function () {
      if (d.item && state.exclude.indexOf(d.item) < 0) state.exclude.push(d.item);
      box.replaceChildren(refinePanel(question, d.choices, "知りたい内容に近いものを選んでください"));
    });
    box.appendChild(yes);
    box.appendChild(no);
    return box;
  }

  // 時間軸と話題の選択肢。選ぶと、却下したページを除いて探し直す
  function refinePanel(question, choices, title) {
    var panel = el("div", "card refine");
    panel.appendChild(el("h2", null, title));
    if (!choices) return panel;
    [["when", "いつの情報？"], ["topic", "何について？"]].forEach(function (g) {
      var list = choices[g[0]] || [];
      if (!list.length) return;
      panel.appendChild(el("p", "note", g[1]));
      var row = el("div", "candidates");
      list.forEach(function (c) {
        var b = el("button", null, c.label);
        b.type = "button";
        if (state.refine[g[0]] === c.value) b.className = "on";
        b.addEventListener("click", function () {
          state.refine[g[0]] = c.value;
          ask(question);
        });
        row.appendChild(b);
      });
      panel.appendChild(row);
    });
    return panel;
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
        li.appendChild(link(null, s.title, s.url));
        ul.appendChild(li);
      });
      root.appendChild(ul);
    });
  }

  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    var q = input.value.trim();
    if (q) newQuestion(q);
  });

  var ex = document.getElementById("examples");
  EXAMPLES.forEach(function (t) {
    var b = el("button", null, t);
    b.type = "button";
    b.addEventListener("click", function () { newQuestion(t); });
    ex.appendChild(b);
  });

  fetch("/api/shortcuts").then(function (r) { return r.json(); }).then(renderShortcuts).catch(function () {});
})();
