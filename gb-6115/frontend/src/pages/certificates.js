import { api } from "../api/workbench.js";
import { errorText, field } from "../components/common/fields.js";
import { empty, section } from "../components/common/panel.js";
import { table } from "../components/common/table.js";
import { submit } from "../hooks/submit.js";
import { RevisionStates } from "../constants/states.js";
import { el } from "../utils/dom.js";
import { cell, time } from "../utils/format.js";

function revisionBadge(value) {
  return el("span", {class: `status state-rev-${value}`, "data-state": value}, RevisionStates[value] || value);
}

function effectiveRows(run, bundle) {
  if (bundle.current_issue) return bundle.current_issue.snapshot.rows;
  return (run.result?.rows || []).map(row => ({...row, "原件证书号": row["退役证书"]}));
}

function correctionForm(run, bundle, refresh) {
  const currentMap = new Map(effectiveRows(run, bundle)
    .filter(row => row["退役证书"] != null)
    .map(row => [row["炉体"], row["退役证书"]]));
  const options = (run.result?.rows || [])
    .filter(row => row["退役证书"] != null)
    .map(row => el("option", {value: row["炉体"]},
      `${row["炉体"]} · 当前 ${currentMap.get(row["炉体"])}`));
  const form = el("form", {id: "correction-form"},
    field("炉体", el("select", {name: "asset", required: true}, options)),
    field("正确证书号", el("input", {name: "certificate_after", required: true, maxlength: 48, pattern: "[A-Z0-9][A-Z0-9-]{0,23}"})),
    field("更正原因", el("textarea", {name: "reason", required: true, minlength: 3, maxlength: 300, rows: 2})),
    errorText(), el("button", {type: "submit"}, "提交更正入稿"));
  submit(form, async values => {
    await api.addCorrection(run.id, {
      asset: values.get("asset"),
      certificate_after: values.get("certificate_after").trim(),
      reason: values.get("reason"),
    });
    form.reset();
    await refresh();
  });
  return form;
}

function issueForm(run, refresh, feedback) {
  const form = el("form", {id: "issue-form"},
    field("签发意见", el("textarea", {name: "note", required: true, minlength: 3, maxlength: 500, rows: 2})),
    errorText(), el("button", {type: "submit"}, "签字并切换新版"));
  submit(form, async values => {
    await api.issueCertificates(run.id, {note: values.get("note")});
    feedback.textContent = "";
    await refresh();
  });
  return form;
}

function pendingPanel(run, bundle, user, refresh) {
  const feedback = errorText();
  const pending = bundle.pending_revisions || [];
  if (!pending.length) {
    return el("div", {class: "stack"}, empty("当前没有待签的更正稿。更正提交后在此汇总，签字后一次性切换。"));
  }
  const allOpened = pending.every(rev => rev.opened_at != null);
  const rows = pending.map(rev => [
    rev.base_serial, rev.asset, rev.certificate_before, rev.certificate_after,
    rev.actor, time(rev.created_at),
    rev.opened_at ? `${rev.opened_by} · ${time(rev.opened_at)}` : "未打开",
  ]);
  const children = [
    table(["代次", "炉体", "原证书号", "正确证书号", "入稿人", "入稿时间", "打开情况"], rows, "待签更正稿"),
  ];
  if (user.role === "reviewer") {
    if (!allOpened) {
      const openBtn = el("button", {type: "button", onclick: async () => {
        openBtn.disabled = true;
        try {
          await api.openCertificates(run.id);
          await refresh();
        } catch (error) {
          feedback.textContent = error.message;
          openBtn.disabled = false;
        }
      }}, "打开待签稿核对");
      children.push(el("p", {class: "empty"}, "打开后若又有更正入稿，这份稿子的签字会被退回，需重新打开最新稿。"), openBtn);
    } else {
      children.push(el("p", {class: "signature"}, el("strong", {}, "已打开核对，可以签字")),
                    issueForm(run, refresh, feedback));
    }
  } else {
    children.push(empty(allOpened ? "复核员已打开待签稿，等待签字。" : "等待复核员打开待签稿。"));
  }
  children.push(feedback);
  return el("div", {class: "stack"}, ...children);
}

function returnedNotice(bundle) {
  const returned = (bundle.revisions || []).filter(rev => rev.status === "returned");
  if (!returned.length) return null;
  return el("div", {class: "panel returned-notice", "data-testid": "returned-notice"},
    el("h2", {}, "已退回的旧待签稿"),
    el("p", {class: "empty"}, "复核员打开后又有更正入稿，旧稿签字退回；记录仍完整留存。"),
    table(["炉体", "原证书号", "拟改证书号", "打开人", "退回原因", "退回时间"],
      returned.map(rev => [rev.asset, rev.certificate_before, rev.certificate_after,
        rev.opened_by || "—", rev.return_note || "—", time(rev.returned_at)]), "退回记录"));
}

function revisionHistory(bundle) {
  const revisions = [...(bundle.revisions || [])].reverse();
  if (!revisions.length) return empty("尚无更正记录。");
  return table(["状态", "炉体", "原证书号", "正确证书号", "入稿人", "入稿时间", "签字人/时间", "签发版本"],
    revisions.map(rev => [
      revisionBadge(rev.status), rev.asset, rev.certificate_before, rev.certificate_after,
      rev.actor, time(rev.created_at),
      rev.signed_at ? `${rev.signed_by} · ${time(rev.signed_at)}` : "—",
      rev.issue_serial ? `v${rev.issue_serial}` : "—",
    ]), "更正记录");
}

function issueHistory(bundle) {
  const issues = [...(bundle.issues || [])].reverse();
  if (!issues.length) return empty("新版签字后，历次签发原件在此留存。");
  return el("div", {class: "stack"}, ...issues.map(issue =>
    el("details", {class: "issue-record"},
      el("summary", {}, `v${issue.version} · ${time(issue.created_at)} · ${issue.actor}`),
      el("p", {}, issue.note),
      el("code", {}, issue.digest),
      table(["炉体", "最后签发证书号", "原件证书号"],
        issue.snapshot.rows.map(row => [row["炉体"], cell(row["退役证书"]), cell(row["原件证书号"])]),
        `签发件 v${issue.version}`))));
}

export function certificatePanel(run, user, bundle, refresh) {
  const current = bundle.current_issue;
  return el("div", {class: "stack certificate-panel", "data-testid": "certificate-panel"},
    section("当前生效证书（最后签发原件）",
      el("p", {class: "empty"},
        current ? `当前为第 ${current.version} 版，由 ${current.actor} 于 ${time(current.created_at)} 签字切换；待签期间此处仍展示最后签发原件。`
          : "尚未签发过新版，当前展示批次原始证书；更正待签期间原件保持可查。"),
      table(["炉体", "退役证书（生效）", "原件证书号", "交卷状态"],
        effectiveRows(run, bundle).map(row =>
          [row["炉体"], cell(row["退役证书"]), cell(row["原件证书号"]), row["交卷状态"]]),
        "当前生效证书")),
    section("待签更正稿", pendingPanel(run, bundle, user, refresh)),
    returnedNotice(bundle),
    user.role === "operator"
      ? section("办理证书更正", correctionForm(run, bundle, refresh))
      : null,
    section("历次签发原件", issueHistory(bundle)),
    section("更正与签字记录", revisionHistory(bundle)));
}
