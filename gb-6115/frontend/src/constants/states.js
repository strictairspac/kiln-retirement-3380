export const States = Object.freeze({
  queued: "等待执行", done: "已完成", failed: "执行失败",
});

export const RevisionStates = Object.freeze({
  pending: "待签", issued: "已签发", returned: "已退回",
});

export const Actions = Object.freeze({
  create_case: "登记资料", enqueue: "提交执行", done: "执行完成", failed: "执行失败", review: "复核签署",
  certificate_correction: "证书更正入稿", certificate_open: "打开待签稿", certificate_issue: "新版证书签发",
});
