"""Cash commands: explicit value checks and atomic cash-only mutations."""

from __future__ import annotations

from fin_ops_platform.services.cash_domain import (
    CASH_SETTLEMENTS,
    SETTLEMENT_KINDS,
    CashError,
    check_version,
    conflict,
    enum,
    fields,
    invalid,
    normalize_bool,
    normalize_date,
    normalize_money,
    normalize_text,
    normalize_uuid,
    normalize_version,
    serialize,
    shanghai_today,
    validate_item_amounts,
)

FLOW_FIELDS = frozenset({"occurred_on", "kind", "amount", "from_account_id", "to_account_id", "category_id", "oa_project_id", "person_name", "content", "remark"})
ITEM_FIELDS = frozenset({"type", "origin_date", "original_amount", "is_opening", "obligation_direction", "ledger_group", "counterparty", "oa_project_id", "bill_label_id", "bill_month", "ticket_provider", "ticket_provided_on", "ticket_description", "related_obligation_id", "ticket_source_id", "content", "remark"})
SETTLEMENT_FIELDS = frozenset({"kind", "amount", "occurred_on", "item_id", "flow_id", "source_item_id", "remark"})
CORRECTION_FIELDS = frozenset({"source_corrections", "settlement_changes", "item_reference_changes", "expected_related_versions"})


def _array(value, name):
    if not isinstance(value, list) or len(value) > 100:
        invalid(f"{name} 必须是至多 100 项的数组。")
    return value


def _project_id(value):
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        invalid("OA 项目 ID 必须是非空字符串。")
    return value


def _month(value):
    if value is None:
        return None
    if not isinstance(value, str) or len(value) != 7:
        invalid("账单月份须为 YYYY-MM。")
    return normalize_date(value + "-01")


class CashService:
    def __init__(self, repository, project_resolver=None, *, stage_validator=None, today=shanghai_today) -> None:
        self.repository = repository
        self.project_resolver = project_resolver
        self.stage_validator = stage_validator
        self.today = today

    def _actual_date(self, value):
        result = normalize_date(value)
        if result > self.today():
            invalid("实际业务日期不能晚于今天。")
        return result

    def _resolve_project(self, project_id, *, historical=False):
        if project_id is None:
            return {"id": None, "name": None, "selection_settings_version": None}
        if self.project_resolver is None:
            raise CashError("cash_dependency_unavailable", "OA 项目只读依赖未配置。", 503)
        result = self.project_resolver(project_id, allow_historical=historical)
        if not isinstance(result, dict) or result.get("id") != project_id or not isinstance(result.get("name"), str) or not result["name"]:
            raise CashError("cash_dependency_unavailable", "OA 项目资料格式不正确。", 503)
        if not historical and type(result.get("selection_settings_version")) is not int:
            raise CashError("cash_dependency_unavailable", "OA 项目校验缺少设置版本。", 503)
        return result

    def _flow_values(self, value):
        required = {"occurred_on", "kind", "amount", "content"}
        value = fields(value, FLOW_FIELDS | {"id"}, required)
        result = {"occurred_on": self._actual_date(value["occurred_on"]), "kind": enum(value["kind"], {"receipt", "payment", "transfer"}),
                  "amount": normalize_money(value["amount"]), "content": normalize_text(value["content"], maximum=1000)}
        for key in ("from_account_id", "to_account_id", "category_id"):
            result[key] = normalize_uuid(value.get(key), nullable=True)
        result["oa_project_id"] = _project_id(value.get("oa_project_id"))
        result["person_name"] = normalize_text(value.get("person_name"), nullable=True)
        result["remark"] = normalize_text(value.get("remark"), maximum=2000, nullable=True)
        if "id" in value:
            result["id"] = normalize_uuid(value["id"])
        origin, target, category = result["from_account_id"], result["to_account_id"], result["category_id"]
        if result["kind"] == "receipt" and not (origin is None and target and category):
            invalid("收款须指定收款账户和适用分类，不得指定付款账户。")
        if result["kind"] == "payment" and not (origin and target is None and category):
            invalid("付款须指定付款账户和适用分类，不得指定收款账户。")
        if result["kind"] == "transfer" and not (origin and target and origin != target and category is None):
            invalid("内部转账须指定两个不同账户，不得指定收支分类。")
        return result

    def _item_values(self, payload, *, related=False):
        value = fields(payload, ITEM_FIELDS | {"id"}, {"id", "type", "origin_date", "original_amount", "content"})
        kind = enum(value["type"], {"loan", "company_receivable", "expense", "ticket_source"})
        if related and kind not in {"loan", "expense"}:
            invalid("现金复合录入只允许新建借款或费用。")
        result = {"id": normalize_uuid(value["id"]), "type": kind, "origin_date": self._actual_date(value["origin_date"]),
                  "original_amount": normalize_money(value["original_amount"]), "is_opening": normalize_bool(value.get("is_opening", False)),
                  "oa_project_id": _project_id(value.get("oa_project_id")), "content": normalize_text(value["content"], maximum=1000),
                  "remark": normalize_text(value.get("remark"), maximum=2000, nullable=True),
                  "origin_flow_id": None, "origin_mode": None}
        for key in ("bill_label_id", "related_obligation_id", "ticket_source_id"):
            result[key] = normalize_uuid(value.get(key), nullable=True)
        result["bill_month"] = _month(value.get("bill_month"))
        for key in ("counterparty", "ticket_provider"):
            result[key] = normalize_text(value.get(key), nullable=True)
        result["ticket_description"] = normalize_text(value.get("ticket_description"), maximum=1000, nullable=True)
        result["ticket_provided_on"] = normalize_date(value.get("ticket_provided_on"), nullable=True)
        result["obligation_direction"] = value.get("obligation_direction")
        result["ledger_group"] = value.get("ledger_group")
        if kind in {"loan", "company_receivable"}:
            result["obligation_direction"] = enum(result["obligation_direction"], {"receivable", "payable"})
            result["ledger_group"] = enum(result["ledger_group"], {"company", "external_person", "personal"})
            if not result["counterparty"]:
                invalid("往来事项必须指定往来对象。")
            if kind == "company_receivable" and (result["obligation_direction"] != "receivable" or result["ledger_group"] != "company"):
                invalid("公司应收的方向和账簿分类不正确。")
            if result["ledger_group"] == "personal" and result["obligation_direction"] != "receivable":
                invalid("个人账只记录明确个人应还义务。")
        elif any(result[key] is not None for key in ("obligation_direction", "ledger_group", "counterparty")) or result["is_opening"]:
            invalid("费用和票据不能指定债务字段或期初。")
        if result["is_opening"] and related:
            invalid("期初旧欠款不能由本次现金生成。")
        if (result["bill_label_id"] is None) != (result["bill_month"] is None) or (kind not in {"loan", "expense"} and result["bill_label_id"] is not None):
            invalid("账单标识和月份须同时提供，且只适用于借款或费用。")
        if kind == "ticket_source":
            if any(result[key] is None for key in ("ticket_provider", "ticket_provided_on", "ticket_description")) or result["ticket_provided_on"] != result["origin_date"]:
                invalid("票据来源须填写提供人、同一提供日期和说明。")
        elif any(result[key] is not None for key in ("ticket_provider", "ticket_provided_on", "ticket_description")):
            invalid("非票据事项不得填写票据来源字段。")
        if result["related_obligation_id"] is not None and kind != "expense":
            invalid("只有费用可以指定往来展示归属。")
        if result["ticket_source_id"] is not None and kind != "company_receivable":
            invalid("只有公司应收可以指定票据来源。")
        if result["id"] in {result["related_obligation_id"], result["ticket_source_id"]}:
            invalid("事项不能引用自身。")
        return result

    def normalize_flow(self, payload, actor, source_kind="manual", task_occurrence_id=None):
        value = fields(payload, FLOW_FIELDS | {"id", "project_mode", "project_item_id", "expected_project_item_version", "related_items", "origin_items", "allocations"}, {"id", "project_mode", "occurred_on", "kind", "amount", "content"})
        mode = enum(value["project_mode"], {"selection", "existing_item"})
        flow = self._flow_values({key: val for key, val in value.items() if key in FLOW_FIELDS | {"id"}})
        flow.update(source_kind=enum(source_kind, {"manual", "monthly_task"}), task_occurrence_id=task_occurrence_id,
                    created_by_account=normalize_text(actor["account"], maximum=500), created_by_name=normalize_text(actor.get("name"), maximum=500, nullable=True))
        related = [self._item_values(item, related=True) for item in _array(value.get("related_items", []), "related_items")]
        origins = []
        for raw in _array(value.get("origin_items", []), "origin_items"):
            raw = fields(raw, {"item_id", "expected_item_version"}, {"item_id", "expected_item_version"})
            origins.append({"item_id": normalize_uuid(raw["item_id"]), "expected_item_version": normalize_version(raw["expected_item_version"])})
        allocations = []
        for raw in _array(value.get("allocations", []), "allocations"):
            raw = fields(raw, {"id", "item_id", "target_is_new", "expected_item_version", "kind", "amount", "remark"}, {"id", "item_id", "target_is_new", "expected_item_version", "kind", "amount"})
            allocations.append({"id": normalize_uuid(raw["id"]), "item_id": normalize_uuid(raw["item_id"]),
                                "target_is_new": normalize_bool(raw["target_is_new"]), "expected_item_version": normalize_version(raw["expected_item_version"], nullable=True),
                                "kind": enum(raw["kind"], CASH_SETTLEMENTS), "amount": normalize_money(raw["amount"]),
                                "remark": normalize_text(raw.get("remark"), maximum=2000, nullable=True)})
        if len(related) + len(origins) + len(allocations) > 100:
            invalid("一次复合录入最多 100 个子操作。")
        item_ids = [item["id"] for item in related] + [item["item_id"] for item in origins]
        if len(set(item_ids)) != len(item_ids) or len({a["id"] for a in allocations}) != len(allocations):
            invalid("同次录入包含重复身份。")
        if len({(a["item_id"], a["kind"]) for a in allocations}) != len(allocations):
            invalid("同一现金、目标及处理类型只能有一条分配，请合并金额。")
        for allocation in allocations:
            is_new = allocation["item_id"] in {item["id"] for item in related}
            if allocation["target_is_new"] != is_new or ((allocation["expected_item_version"] is None) != is_new):
                invalid("分配目标的新建身份和预期版本不匹配。")
        if flow["kind"] == "transfer" and (related or origins or allocations or task_occurrence_id):
            invalid("内部转账不能产生事项、分配或收付任务。")
        context = {"project_mode": mode}
        if mode == "existing_item":
            if any(key in value for key in ("oa_project_id", "related_items", "origin_items")) or flow["kind"] == "transfer":
                invalid("历史事项结算不接受改选项目、新事项、补本金或内部转账。")
            anchor = normalize_uuid(value.get("project_item_id"))
            version = normalize_version(value.get("expected_project_item_version"))
            if not any(a["item_id"] == anchor and a["expected_item_version"] == version and not a["target_is_new"] for a in allocations):
                invalid("历史项目锚点必须实际参与本次正额结算。")
            context.update(project_item_id=anchor, expected_project_item_version=version)
        elif "project_item_id" in value or "expected_project_item_version" in value:
            invalid("自由选择项目不接受历史事项锚点。")
        return {"flow": flow, "related_items": related, "origin_items": origins, "allocations": allocations, "context": context}

    def prepare_flow(self, normalized):
        flow, context = normalized["flow"], normalized["context"]
        if context["project_mode"] == "existing_item":
            with self.repository.transaction(readonly=True) as tx:
                anchor = tx.get("items", context["project_item_id"])
            flow["oa_project_id"], flow["project_name_snapshot"] = anchor["oa_project_id"], anchor["project_name_snapshot"]
            context["selection_settings_version"] = None
        else:
            project = self._resolve_project(flow["oa_project_id"])
            flow["project_name_snapshot"] = project["name"]
            context["selection_settings_version"] = project.get("selection_settings_version")
        for item in normalized["related_items"]:
            if item["oa_project_id"] is not None and item["oa_project_id"] != flow["oa_project_id"]:
                invalid("本次新事项的项目必须与现金一致。")
            if item["origin_date"] != flow["occurred_on"]:
                invalid("来源事项的实际日期必须与现金一致。")
            item.update(oa_project_id=flow["oa_project_id"], project_name_snapshot=flow["project_name_snapshot"], origin_flow_id=flow["id"], origin_mode="created")
        return normalized

    def replay_flow(self, normalized, tx=None):
        if tx is None:
            with self.repository.transaction(readonly=True) as own:
                return self.replay_flow(normalized, own)
        flow = normalized["flow"]
        if tx.was_deleted("flow", flow["id"]):
            conflict("此提交已被删除，不能重新创建。", "cash_submission_deleted")
        existing = tx.get("flows", flow["id"], required=False)
        if existing is None:
            if tx.was_deleted("flow", flow["id"]):
                conflict("此提交已被删除，不能重新创建。", "cash_submission_deleted")
            return None
        context = normalized["context"]
        expected_project = flow["oa_project_id"]
        if context["project_mode"] == "existing_item":
            anchor = tx.get("items", context["project_item_id"])
            expected_project = anchor["oa_project_id"]
        keys = FLOW_FIELDS | {"source_kind"}
        if existing["version"] != 1 or any(existing[key] != (expected_project if key == "oa_project_id" else flow[key]) for key in keys):
            conflict("同一流水 ID 已用于不同或已修改的业务。", "cash_submission_conflict")
        if flow["task_occurrence_id"] is not None and existing["task_occurrence_id"] != flow["task_occurrence_id"]:
            conflict("流水任务归属不同。", "cash_submission_conflict")
        related = tx.rows("items", {"origin_flow_id": flow["id"]})
        created = {item["id"]: item for item in related if item["origin_mode"] == "created"}
        linked = {item["id"]: item for item in related if item["origin_mode"] == "linked"}
        if set(created) != {item["id"] for item in normalized["related_items"]} or set(linked) != {item["item_id"] for item in normalized["origin_items"]}:
            conflict("流水关联事项与原提交不同。", "cash_submission_conflict")
        for item in normalized["related_items"]:
            stored = created[item["id"]]
            if stored["version"] != 1 or any(stored[key] != (expected_project if key == "oa_project_id" else item[key]) for key in ITEM_FIELDS):
                conflict("流水子事项已变化。", "cash_submission_conflict")
        allocations = tx.rows("settlements", {"flow_id": flow["id"]})
        expected = {a["id"]: a for a in normalized["allocations"]}
        if {a["id"] for a in allocations} != set(expected):
            conflict("流水分配与原提交不同。", "cash_submission_conflict")
        for allocation in allocations:
            if allocation["version"] != 1 or any(allocation[key] != expected[allocation["id"]][key] for key in ("item_id", "kind", "amount", "remark")):
                conflict("流水分配已变化。", "cash_submission_conflict")
        return {"flow": existing, "related_items": list(created.values()), "origin_items": list(linked.values()), "allocations": allocations, "version": existing["version"], "created": False}

    def create_flow(self, payload, actor):
        normalized = self.normalize_flow(payload, actor)
        replay = self.replay_flow(normalized)
        if replay is not None:
            return serialize(replay)
        prepared = self.prepare_flow(normalized)
        with self.repository.transaction() as tx:
            return serialize(self.create_flow_in_transaction(tx, prepared))

    def lock_flow_config(self, tx, flows, related_items=(), selection_version=None):
        if selection_version is not None or any(item.get("ledger_group") == "personal" for item in related_items):
            settings = tx.get("settings", 1, "share")
            if selection_version is not None and settings["version"] != selection_version:
                conflict("项目允许状态配置已变化，请重新选择。", "cash_project_selection_changed")
        category_ids = {flow["category_id"] for flow in flows if flow["category_id"]}
        categories = tx.lock_rows("categories", category_ids, "share")
        bill_ids = {item["bill_label_id"] for item in related_items if item.get("bill_label_id")}
        labels = tx.lock_rows("bill_labels", bill_ids, "share")
        accounts = tx.lock_rows("accounts", {flow[key] for flow in flows for key in ("from_account_id", "to_account_id") if flow[key]}, "share")
        for flow in flows:
            for key in ("from_account_id", "to_account_id"):
                if flow[key]:
                    account = accounts.get(flow[key])
                    if account is None:
                        raise CashError("cash_not_found", "现金账户不存在。", 404)
                    if not account["enabled"] or flow["occurred_on"] < account["opening_date"]:
                        conflict("账户已停用或现金日期早于账户起算日。")
            if flow["category_id"]:
                category = categories.get(flow["category_id"])
                if category is None:
                    raise CashError("cash_not_found", "现金分类不存在。", 404)
                if not category["enabled"] or category["group"] not in {flow["kind"], "turnover"}:
                    conflict("现金分类已停用或不适用于本次方向。")
        for item in related_items:
            if item.get("bill_label_id") and (item["bill_label_id"] not in labels or not labels[item["bill_label_id"]]["enabled"]):
                conflict("账单标识不存在或已停用。")

    def _validate_item(self, tx, item):
        if item["ledger_group"] == "personal":
            start = tx.get("settings", 1)["personal_opening_date"]
            if start is None:
                conflict("请先设置个人账记账起点。")
            if item["origin_date"] < start or (item["is_opening"] and item["origin_date"] != start):
                conflict("个人事项日期与记账起点不符。")
        for key, types in (("related_obligation_id", {"loan", "company_receivable"}), ("ticket_source_id", {"ticket_source"})):
            if item[key]:
                target = tx.get("items", item[key])
                if target["type"] not in types or target["oa_project_id"] != item["oa_project_id"]:
                    conflict("事项引用的类型或项目不匹配。")
        if item["origin_flow_id"]:
            flow = tx.get("flows", item["origin_flow_id"])
            direction = "payment" if item["type"] == "expense" or item["obligation_direction"] == "receivable" else "receipt"
            if flow["kind"] != direction or flow["oa_project_id"] != item["oa_project_id"] or flow["occurred_on"] != item["origin_date"]:
                conflict("来源现金的方向、项目或日期不匹配。")

    def _validate_settlement(self, tx, settlement):
        kind = settlement["kind"]
        target = tx.get("items", settlement["item_id"]) if settlement["item_id"] else None
        source = tx.get("items", settlement["source_item_id"]) if settlement["source_item_id"] else None
        flow = tx.get("flows", settlement["flow_id"]) if settlement["flow_id"] else None
        if kind in CASH_SETTLEMENTS:
            if target is None or flow is None or source is not None:
                invalid("现金分配必须关联真实现金和事项，不得指定非现金来源。")
            expected_type = {"cash_repayment": "loan", "company_collection": "company_receivable", "expense_payment": "expense", "expense_refund": "expense"}[kind]
            expected_direction = "payment" if kind == "expense_payment" or (kind == "cash_repayment" and target["obligation_direction"] == "payable") else "receipt"
            if target["type"] != expected_type or flow["kind"] != expected_direction:
                conflict("分配类型、事项或现金方向不一致。")
            if flow["occurred_on"] != settlement["occurred_on"] or flow["oa_project_id"] != target["oa_project_id"]:
                conflict("分配日期或项目与现金不一致。")
            if kind == "expense_payment" and target["origin_flow_id"] == flow["id"]:
                conflict("来源现金已支付该费用，不能重复分配。")
        else:
            if flow is not None:
                invalid("非现金处理不能关联现金流水。")
            if kind == "ticket_use":
                if target is not None or source is None or source["type"] != "ticket_source" or not settlement["remark"]:
                    invalid("票据使用须有票据来源及用途，不得指定抵债目标。")
            elif target is None or target["type"] not in {"loan", "company_receivable"}:
                invalid("冲抵须指定借款或公司应收。")
            if kind == "ticket_offset" and (source is None or source["type"] != "ticket_source"):
                invalid("票抵须指定票据来源。")
            if kind == "non_ticket_offset" and ((source and source["type"] != "expense") or (source is None and not settlement["remark"])):
                invalid("无票冲抵须指定费用来源，或填写明确调整原因。")
            if source and target and source["oa_project_id"] != target["oa_project_id"]:
                conflict("非现金来源与目标项目不同。")
        if target and settlement["occurred_on"] < target["origin_date"] or source and settlement["occurred_on"] < source["origin_date"]:
            conflict("处理日期不能早于来源或目标发生日。")

    def _validate_balances(self, tx, item_ids, flow_ids):
        settlements = tx.settlements_for_items(item_ids)
        for item_id in sorted(set(item_ids)):
            item = tx.get("items", item_id, required=False)
            if item:
                self._validate_item(tx, item)
                validate_item_amounts(item, settlements)
        for flow_id in sorted(set(flow_ids)):
            flow = tx.get("flows", flow_id, required=False)
            if flow:
                budget = tx.flow_budget(flow_id)
                if budget["obligation"] > flow["amount"] or budget["expense"] > flow["amount"]:
                    conflict("分配超过现金的义务资金或费用口径额度。")
        for settlement in settlements:
            self._validate_settlement(tx, settlement)

    def create_flow_in_transaction(self, tx, prepared):
        replay = self.replay_flow(prepared, tx)
        if replay is not None:
            return replay
        flow, context = prepared["flow"], prepared["context"]
        related, origins, allocations = prepared["related_items"], prepared["origin_items"], prepared["allocations"]
        self.lock_flow_config(tx, [flow], related, context.get("selection_settings_version"))
        if flow["task_occurrence_id"]:
            occurrence = tx.get("task_occurrences", flow["task_occurrence_id"], "update")
            if occurrence["template_values_snapshot"]["kind"] != flow["kind"]:
                conflict("任务与现金方向不同。")
        # Claim the flow identity before locking target items. A concurrent identical
        # creator must replay the committed result before checking its old target CAS.
        inserted = tx.insert("flows", flow)
        if inserted is None:
            replay = self.replay_flow(prepared, tx)
            if replay is None:
                conflict("流水提交状态已经改变。", "cash_submission_conflict")
            return replay
        target_ids = {a["item_id"] for a in allocations if not a["target_is_new"]} | {item["item_id"] for item in origins}
        target_ids |= {item[key] for item in related for key in ("related_obligation_id", "ticket_source_id") if item[key] and item[key] not in {r["id"] for r in related}}
        targets = tx.lock_rows("items", target_ids)
        for entry in origins:
            item = targets.get(entry["item_id"])
            if item is None:
                raise CashError("cash_not_found", "补录来源事项不存在。", 404)
            check_version(item, entry["expected_item_version"])
            if item["type"] != "loan" or item["is_opening"] or item["origin_flow_id"] is not None:
                conflict("只有无现金来源的真实非期初借款可以补录绑定。")
        for allocation in allocations:
            if not allocation["target_is_new"]:
                target = targets.get(allocation["item_id"])
                if target is None:
                    raise CashError("cash_not_found", "结算目标不存在。", 404)
                check_version(target, allocation["expected_item_version"])
        if context["project_mode"] == "existing_item":
            anchor = targets[context["project_item_id"]]
            check_version(anchor, context["expected_project_item_version"])
            if (anchor["oa_project_id"], anchor["project_name_snapshot"]) != (flow["oa_project_id"], flow["project_name_snapshot"]):
                conflict("历史事项项目已变化。", "cash_version_conflict")
        for item in sorted(related, key=lambda row: (row["type"] != "loan", row["id"])):
            if tx.was_deleted("item", item["id"]):
                conflict("事项提交已经删除。", "cash_submission_deleted")
            if tx.insert("items", item) is None:
                conflict("事项 ID 已被使用。", "cash_submission_conflict")
            if tx.was_deleted("item", item["id"]):
                conflict("事项提交已经删除。", "cash_submission_deleted")
        for entry in origins:
            tx.update("items", entry["item_id"], {"origin_flow_id": flow["id"], "origin_mode": "linked"})
        for allocation in allocations:
            row = {key: allocation[key] for key in ("id", "item_id", "kind", "amount", "remark")}
            row.update(flow_id=flow["id"], occurred_on=flow["occurred_on"], source_item_id=None)
            self._validate_settlement(tx, row)
            if tx.insert("settlements", row) is None:
                conflict("分配 ID 已被使用。", "cash_submission_conflict")
        all_item_ids = target_ids | {item["id"] for item in related}
        self._validate_balances(tx, all_item_ids, {flow["id"]})
        for item_id in {a["item_id"] for a in allocations}:
            tx.update("items", item_id, {})
        if tx.was_deleted("flow", flow["id"]):
            conflict("原提交已删除，不能由延迟请求重新建立。", "cash_submission_deleted")
        return {"flow": inserted, "related_items": [tx.get("items", item["id"]) for item in related],
                "origin_items": [tx.get("items", item["item_id"]) for item in origins],
                "allocations": tx.rows("settlements", {"flow_id": flow["id"]}), "version": 1, "created": True}

    def _configuration_values(self, table, payload, *, updating=False):
        allowed = {
            "accounts": {"name", "kind", "opening_date", "opening_amount", "enabled", "remark"},
            "categories": {"name", "group", "enabled", "remark"},
            "bill_labels": {"bank_name", "label", "enabled"},
        }[table]
        required = {"accounts": {"id", "name", "kind", "opening_date", "opening_amount"},
                    "categories": {"id", "name", "group"}, "bill_labels": {"id", "bank_name", "label"}}[table]
        value = fields(payload, allowed | ({"expected_version"} if updating else {"id"}), {"expected_version"} if updating else required)
        result = {}
        for key, raw in value.items():
            if key == "expected_version":
                normalize_version(raw)
            elif key == "id":
                result[key] = normalize_uuid(raw)
            elif key == "enabled":
                result[key] = normalize_bool(raw)
            elif key == "opening_date":
                result[key] = self._actual_date(raw)
            elif key == "opening_amount":
                result[key] = normalize_money(raw, signed=True)
            elif key == "kind":
                result[key] = enum(raw, {"cash", "savings"})
            elif key == "group":
                result[key] = enum(raw, {"receipt", "payment", "turnover"})
            else:
                result[key] = normalize_text(raw, maximum=2000 if key == "remark" else 120, nullable=key == "remark")
        if not updating:
            result.setdefault("enabled", True)
            if table != "bill_labels":
                result.setdefault("remark", None)
        elif not result:
            invalid("更正请求没有可修改字段。")
        return result

    def _create_configuration(self, table, payload):
        values = self._configuration_values(table, payload)
        with self.repository.transaction() as tx:
            inserted = tx.insert(table, values)
            if inserted is None:
                inserted = tx.get(table, values["id"])
                if inserted["version"] != 1 or any(inserted[key] != value for key, value in values.items()):
                    conflict("配置 ID 已用于不同内容。", "cash_submission_conflict")
            return serialize({{"accounts": "account", "categories": "category", "bill_labels": "bill_label"}[table]: inserted, "version": inserted["version"]})

    def _update_configuration(self, table, entity_id, payload):
        entity_id = normalize_uuid(entity_id)
        changes = self._configuration_values(table, payload, updating=True)
        with self.repository.transaction() as tx:
            old = tx.get(table, entity_id, "update")
            check_version(old, payload["expected_version"])
            actual = {key: value for key, value in changes.items() if old[key] != value}
            if table == "accounts":
                earliest = tx.earliest_account_flow(entity_id)
                if "opening_date" in actual and earliest is not None and actual["opening_date"] > earliest:
                    conflict("新起算日会排除已经存在的现金流水。")
                if "kind" in actual and tx.account_is_referenced(entity_id):
                    conflict("已引用账户不能改变资金性质，请新建账户。")
            if table == "categories" and "group" in actual and tx.category_is_referenced(entity_id):
                conflict("已引用分类不能改变方向含义，请新建分类。")
            row = tx.update(table, entity_id, actual) if actual else old
            return serialize({{"accounts": "account", "categories": "category", "bill_labels": "bill_label"}[table]: row, "version": row["version"], "changed": bool(actual)})

    def create_account(self, payload):
        return self._create_configuration("accounts", payload)

    def update_account(self, entity_id, payload):
        return self._update_configuration("accounts", entity_id, payload)

    def create_category(self, payload):
        return self._create_configuration("categories", payload)

    def update_category(self, entity_id, payload):
        return self._update_configuration("categories", entity_id, payload)

    def create_bill_label(self, payload):
        return self._create_configuration("bill_labels", payload)

    def update_bill_label(self, entity_id, payload):
        return self._update_configuration("bill_labels", entity_id, payload)

    def get_project_selection(self):
        with self.repository.transaction(readonly=True) as tx:
            row = tx.get("settings", 1)
            return {"version": row["version"], "allowed_stage_codes": row["allowed_project_stage_codes"], "configured": row["project_selection_configured"]}

    def update_project_selection(self, payload):
        value = fields(payload, {"expected_version", "allowed_stage_codes"}, {"expected_version", "allowed_stage_codes"})
        codes = _array(value["allowed_stage_codes"], "allowed_stage_codes")
        if any(not isinstance(code, str) or not code for code in codes) or len(set(codes)) != len(codes):
            invalid("允许项目状态必须为不重复的真实状态代码。")
        normalize_version(value["expected_version"])
        if self.stage_validator is None:
            raise CashError("cash_dependency_unavailable", "OA 状态字典依赖未配置。", 503)
        self.stage_validator(codes)
        with self.repository.transaction() as tx:
            row = tx.get("settings", 1, "update")
            check_version(row, value["expected_version"])
            changed = not row["project_selection_configured"] or set(row["allowed_project_stage_codes"]) != set(codes)
            if changed:
                row = tx.update("settings", 1, {"allowed_project_stage_codes": sorted(codes), "project_selection_configured": True})
            return {"version": row["version"], "allowed_stage_codes": row["allowed_project_stage_codes"], "configured": row["project_selection_configured"], "changed": changed}

    def get_personal_opening(self):
        with self.repository.transaction(readonly=True) as tx:
            row = tx.get("settings", 1)
            return serialize({"opening_date": row["personal_opening_date"], "version": row["version"]})

    def update_personal_opening(self, payload):
        value = fields(payload, {"expected_version", "opening_date"}, {"expected_version", "opening_date"})
        opening = self._actual_date(value["opening_date"]) if value["opening_date"] is not None else None
        with self.repository.transaction() as tx:
            settings = tx.get("settings", 1, "update")
            check_version(settings, value["expected_version"])
            items = tx.personal_items()
            tx.lock_rows("items", [item["id"] for item in items])
            settlements = tx.settlements_for_items([item["id"] for item in items])
            if items and opening is None:
                conflict("存在个人事项时不能清空记账起点。")
            if opening is not None:
                if any(not item["is_opening"] and item["origin_date"] < opening for item in items) or any(s["occurred_on"] < opening for s in settlements):
                    conflict("新起算日会排除已有个人本金或结算。")
            changed = settings["personal_opening_date"] != opening
            if changed:
                settings = tx.update("settings", 1, {"personal_opening_date": opening})
                for item in items:
                    if item["is_opening"]:
                        tx.update("items", item["id"], {"origin_date": opening})
            return serialize({"opening_date": opening, "version": settings["version"], "changed": changed})

    @staticmethod
    def _versions(value):
        value = fields(value, {"flows", "items", "occurrences"})
        output = {"flows": {}, "items": {}, "occurrences": {}}
        for kind in output:
            for raw in _array(value.get(kind, []), "expected_related_versions." + kind):
                raw = fields(raw, {"id", "version"}, {"id", "version"})
                entity_id = normalize_uuid(raw["id"])
                if entity_id in output[kind]:
                    invalid("预期版本集合存在重复对象。")
                output[kind][entity_id] = normalize_version(raw["version"])
        return output

    @staticmethod
    def _require_version(row, versions, kind, tx=None):
        if row["id"] not in versions[kind]:
            invalid("缺少关联对象的预期版本。")
        table = "task_occurrences" if kind == "occurrences" else kind
        if tx is not None and (table, row["id"]) in tx._bumped:
            row = {**row, "version": row["version"]-1}
        check_version(row, versions[kind][row["id"]])

    def create_item(self, payload, actor=None):
        value = fields(payload, ITEM_FIELDS | {"id", "expected_related_versions"}, {"id", "type", "origin_date", "original_amount", "content"})
        item = self._item_values({key: val for key, val in value.items() if key != "expected_related_versions"})
        versions = self._versions(value.get("expected_related_versions", {}))
        with self.repository.transaction(readonly=True) as tx:
            if tx.was_deleted("item", item["id"]):
                conflict("事项已被删除。", "cash_submission_deleted")
            old = tx.get("items", item["id"], required=False)
            if old:
                if old["version"] != 1 or any(old[key] != item[key] for key in ITEM_FIELDS):
                    conflict("同一事项 ID 已用于不同或已修改内容。", "cash_submission_conflict")
                return serialize({"item": old, "version": old["version"], "created": False})
        project = self._resolve_project(item["oa_project_id"], historical=item["is_opening"])
        item["project_name_snapshot"] = project["name"]
        with self.repository.transaction() as tx:
            self.lock_flow_config(tx, [], [item], None if item["is_opening"] else project.get("selection_settings_version"))
            refs = tx.lock_rows("items", [item["related_obligation_id"], item["ticket_source_id"]])
            for row in refs.values():
                self._require_version(row, versions, "items")
            if tx.was_deleted("item", item["id"]):
                conflict("事项已被删除。", "cash_submission_deleted")
            inserted = tx.insert("items", item)
            if inserted is None:
                old = tx.get("items", item["id"], required=False)
                if old is None and tx.was_deleted("item", item["id"]):
                    conflict("原事项提交已删除。", "cash_submission_deleted")
                if old is None or old["version"] != 1 or any(old[key] != item[key] for key in ITEM_FIELDS):
                    conflict("事项 ID 已被使用。", "cash_submission_conflict")
                return serialize({"item": old, "version": old["version"], "created": False})
            self._validate_item(tx, inserted)
            if tx.was_deleted("item", item["id"]):
                conflict("原事项提交已删除。", "cash_submission_deleted")
            return serialize({"item": inserted, "version": 1, "created": True})

    def _lock_graph(self, tx, *, flow_ids=(), item_ids=(), extra_flows=(), extra_items=(), config_flows=(), config_items=(), selection_version=None, creating_settlement_id=None):
        flow_ids = sorted(set(flow_ids) | set(extra_flows))
        item_ids = sorted(set(item_ids) | set(extra_items))
        graph = tx.relations(flow_ids=flow_ids, item_ids=item_ids)
        flows = [tx.get("flows", entity_id) for entity_id in graph["flow_ids"]]
        items = [tx.get("items", entity_id) for entity_id in graph["item_ids"]]
        if selection_version is not None or any(item["ledger_group"] == "personal" for item in [*items, *config_items]):
            settings = tx.get("settings", 1, "share")
            if selection_version is not None and settings["version"] != selection_version:
                conflict("项目允许状态配置已变化。", "cash_project_selection_changed")
        tx.lock_rows("categories", [flow["category_id"] for flow in [*flows, *config_flows]], "share")
        tx.lock_rows("bill_labels", [item["bill_label_id"] for item in [*items, *config_items]], "share")
        tx.lock_rows("accounts", [flow[key] for flow in [*flows, *config_flows] for key in ("from_account_id", "to_account_id")], "share")
        occurrences = tx.lock_rows("task_occurrences", [flow["task_occurrence_id"] for flow in flows])
        locked_flows = tx.lock_rows("flows", graph["flow_ids"])
        locked_items = tx.lock_rows("items", graph["item_ids"])
        tx.lock_rows("settlements", [row["id"] for row in graph["settlements"]])
        fresh = tx.relations(flow_ids=flow_ids, item_ids=item_ids)
        old_settlements = {s["id"] for s in graph["settlements"]}
        fresh_settlements = {s["id"] for s in fresh["settlements"]}
        own_concurrent_insert = creating_settlement_id is not None and fresh_settlements - old_settlements == {creating_settlement_id} and not old_settlements - fresh_settlements
        if graph["flow_ids"] != fresh["flow_ids"] or graph["item_ids"] != fresh["item_ids"] or (old_settlements != fresh_settlements and not own_concurrent_insert):
            conflict("关联记录已变化，请刷新后重新确认。", "cash_version_conflict")
        if own_concurrent_insert:
            tx.get("settlements", creating_settlement_id, "update")
        if len(locked_flows) != len(graph["flow_ids"]) or len(locked_items) != len(graph["item_ids"]):
            conflict("关联记录已删除。", "cash_version_conflict")
        fresh.update(flows=locked_flows, items=locked_items, occurrences=occurrences)
        return fresh

    @staticmethod
    def _bump_settlement_objects(tx, settlement):
        for key in ("item_id", "source_item_id"):
            if settlement[key] and tx.get("items", settlement[key], required=False):
                tx.update("items", settlement[key], {})
        if settlement["flow_id"]:
            flow = tx.get("flows", settlement["flow_id"], required=False)
            if flow:
                tx.update("flows", flow["id"], {})
                if flow["task_occurrence_id"]:
                    tx.update("task_occurrences", flow["task_occurrence_id"], {})

    def _settlement_values(self, value):
        value = fields(value, SETTLEMENT_FIELDS | {"id"}, {"id", "kind", "amount", "occurred_on"})
        result = {"id": normalize_uuid(value["id"]), "kind": enum(value["kind"], SETTLEMENT_KINDS), "amount": normalize_money(value["amount"]),
                  "occurred_on": self._actual_date(value["occurred_on"]), "remark": normalize_text(value.get("remark"), maximum=2000, nullable=True)}
        for key in ("item_id", "flow_id", "source_item_id"):
            result[key] = normalize_uuid(value.get(key), nullable=True)
        if result["item_id"] is not None and result["item_id"] == result["source_item_id"]:
            invalid("来源事项和目标事项不能相同。")
        return result

    def create_settlement(self, payload, actor=None):
        expected_keys = {"expected_item_version", "expected_flow_version", "expected_source_item_version"}
        value = fields(payload, SETTLEMENT_FIELDS | {"id"} | expected_keys, {"id", "kind", "amount", "occurred_on"})
        settlement = self._settlement_values({key: val for key, val in value.items() if key not in expected_keys})
        for entity, version in (("item_id", "expected_item_version"), ("flow_id", "expected_flow_version"), ("source_item_id", "expected_source_item_version")):
            if settlement[entity] is not None:
                normalize_version(value.get(version))
            elif value.get(version) is not None:
                invalid("不存在的关联对象不能指定版本。")
        with self.repository.transaction() as tx:
            old = tx.get("settlements", settlement["id"], required=False)
            if old:
                if old["version"] != 1 or any(old[key] != val for key, val in settlement.items()):
                    conflict("分配 ID 已用于不同或已更正的内容。", "cash_submission_conflict")
                return serialize({"settlement": old, "version": old["version"], "created": False})
            graph = self._lock_graph(tx, flow_ids=[settlement["flow_id"]] if settlement["flow_id"] else [], item_ids=[key for key in (settlement["item_id"], settlement["source_item_id"]) if key], creating_settlement_id=settlement["id"])
            concurrent = tx.get("settlements", settlement["id"], required=False)
            if concurrent:
                if concurrent["version"] != 1 or any(concurrent[key] != val for key, val in settlement.items()):
                    conflict("分配提交已用于不同内容。", "cash_submission_conflict")
                return serialize({"settlement": concurrent, "version": 1, "created": False})
            for entity, version, table in (("item_id", "expected_item_version", "items"), ("source_item_id", "expected_source_item_version", "items"), ("flow_id", "expected_flow_version", "flows")):
                if settlement[entity]:
                    check_version(tx.get(table, settlement[entity]), value[version])
            self._validate_settlement(tx, settlement)
            self._check_unique_cash_allocation(tx, settlement)
            if tx.insert("settlements", settlement) is None:
                conflict("分配提交已被并发处理，请刷新。", "cash_submission_conflict")
            self._validate_balances(tx, graph["item_ids"], graph["flow_ids"])
            self._bump_settlement_objects(tx, settlement)
            return serialize({"settlement": tx.get("settlements", settlement["id"]), "version": 1, "created": True, **self._affected(tx, graph)})

    def _change_settlement(self, tx, old, changes, versions):
        for column, table, kind in (("item_id", "items", "items"), ("source_item_id", "items", "items"), ("flow_id", "flows", "flows")):
            for entity_id in {old[column], changes.get(column, old[column])} - {None}:
                self._require_version(tx.get(table, entity_id), versions, kind, tx)
        new = {**old, **changes}
        if old["kind"] != new["kind"] and {old["kind"], new["kind"]} != {"ticket_use", "ticket_offset"}:
            invalid("处理类型只能在同次票据使用与票抵之间更正。")
        self._validate_settlement(tx, new)
        self._check_unique_cash_allocation(tx, new)
        row = tx.update("settlements", old["id"], changes)
        self._bump_settlement_objects(tx, old)
        self._bump_settlement_objects(tx, new)
        return row

    @staticmethod
    def _check_unique_cash_allocation(tx, settlement):
        if settlement["flow_id"] is None:
            return
        matches = tx.rows("settlements", {"flow_id": settlement["flow_id"], "item_id": settlement["item_id"], "kind": settlement["kind"]})
        if any(row["id"] != settlement["id"] for row in matches):
            conflict("该现金对同一事项已有同类分配，请更正原分配金额。")

    def update_settlement(self, entity_id, payload, actor=None):
        entity_id = normalize_uuid(entity_id)
        value = fields(payload, SETTLEMENT_FIELDS | {"expected_version", "expected_related_versions"}, {"expected_version", "expected_related_versions"})
        changes = {key: val for key, val in value.items() if key in SETTLEMENT_FIELDS}
        if not changes:
            invalid("更正请求没有可修改字段。")
        versions = self._versions(value["expected_related_versions"])
        with self.repository.transaction() as tx:
            old = tx.get("settlements", entity_id)
            proposed = self._settlement_values({**serialize({key: old[key] for key in SETTLEMENT_FIELDS | {"id"}}), **changes})
            graph = self._lock_graph(tx, flow_ids=[key for key in (old["flow_id"], proposed["flow_id"]) if key], item_ids=[key for key in (old["item_id"], old["source_item_id"], proposed["item_id"], proposed["source_item_id"]) if key])
            old = tx.get("settlements", entity_id, "update")
            check_version(old, value["expected_version"])
            actual = {key: val for key, val in proposed.items() if key != "id" and old[key] != val}
            row = self._change_settlement(tx, old, actual, versions) if actual else old
            self._validate_balances(tx, graph["item_ids"], graph["flow_ids"])
            return serialize({"settlement": row, "version": row["version"], "changed": bool(actual), **self._affected(tx, graph)})

    def delete_settlement(self, entity_id, payload, actor=None):
        entity_id = normalize_uuid(entity_id)
        value = fields(payload, {"expected_version", "expected_related_versions"}, {"expected_version", "expected_related_versions"})
        versions = self._versions(value["expected_related_versions"])
        with self.repository.transaction() as tx:
            old = tx.get("settlements", entity_id)
            graph = self._lock_graph(tx, flow_ids=[old["flow_id"]] if old["flow_id"] else [], item_ids=[key for key in (old["item_id"], old["source_item_id"]) if key])
            old = tx.get("settlements", entity_id, "update")
            check_version(old, value["expected_version"])
            for column, table, kind in (("item_id", "items", "items"), ("source_item_id", "items", "items"), ("flow_id", "flows", "flows")):
                if old[column]:
                    self._require_version(tx.get(table, old[column]), versions, kind)
            tx.delete("settlements", entity_id)
            self._bump_settlement_objects(tx, old)
            self._validate_balances(tx, graph["item_ids"], graph["flow_ids"])
            return serialize({"id": entity_id, "removed": True, **self._affected(tx, graph)})

    @staticmethod
    def _affected(tx, graph, *, removed_settlements=0):
        items, occurrences = [], []
        for entity_id in graph["item_ids"]:
            if ("items", entity_id) in tx._bumped:
                row = tx.get("items", entity_id, required=False)
                if row:
                    items.append({"id": entity_id, "version": row["version"]})
        for entity_id in graph.get("occurrences", {}):
            if ("task_occurrences", entity_id) in tx._bumped:
                row = tx.get("task_occurrences", entity_id, required=False)
                if row:
                    occurrences.append({"id": entity_id, "version": row["version"]})
        removed_items = sum(table == "items" for table, _ in tx._deleted)
        return {"affected_counts": {"items": len(items)+removed_items, "tasks": len(occurrences), "settlements": removed_settlements},
                "affected_items": items[:20], "affected_tasks": occurrences[:20], "affected_preview_truncated": len(items) > 20 or len(occurrences) > 20}

    def _corrections(self, payload):
        versions = self._versions(payload.get("expected_related_versions", {}))
        sources, settlements, refs = [], [], []
        for raw in _array(payload.get("source_corrections", []), "source_corrections"):
            raw = fields(raw, {"action", "item_id", "expected_version", "original_amount", "new_flow_id", "expected_new_flow_version"}, {"action", "item_id", "expected_version"})
            action = enum(raw["action"], {"correct_amount", "delete_false_item", "keep_independent", "rebind_flow"})
            row = {"action": action, "item_id": normalize_uuid(raw["item_id"]), "expected_version": normalize_version(raw["expected_version"])}
            extras = set(raw) - {"action", "item_id", "expected_version"}
            required = {"correct_amount": {"original_amount"}, "rebind_flow": {"new_flow_id", "expected_new_flow_version"}, "delete_false_item": set(), "keep_independent": set()}[action]
            if extras != required:
                invalid("来源纠错字段与所选动作不一致。")
            if action == "correct_amount":
                row["original_amount"] = normalize_money(raw["original_amount"])
            if action == "rebind_flow":
                row.update(new_flow_id=normalize_uuid(raw["new_flow_id"]), expected_new_flow_version=normalize_version(raw["expected_new_flow_version"]))
            sources.append(row)
        for raw in _array(payload.get("settlement_changes", []), "settlement_changes"):
            raw = fields(raw, {"id", "expected_version", "action", "fields"}, {"id", "expected_version", "action"})
            action = enum(raw["action"], {"remove", "update"})
            if ("fields" in raw) != (action == "update"):
                invalid("分配更正动作与字段不一致。")
            row = {"id": normalize_uuid(raw["id"]), "expected_version": normalize_version(raw["expected_version"]), "action": action}
            if action == "update":
                row["fields"] = fields(raw["fields"], SETTLEMENT_FIELDS)
                if not row["fields"]:
                    invalid("分配更正字段不能为空。")
            settlements.append(row)
        for raw in _array(payload.get("item_reference_changes", []), "item_reference_changes"):
            raw = fields(raw, {"item_id", "expected_version", "related_obligation_id", "ticket_source_id"}, {"item_id", "expected_version"})
            if len(raw) < 3:
                invalid("引用更正必须明确一个引用字段。")
            row = {"item_id": normalize_uuid(raw["item_id"]), "expected_version": normalize_version(raw["expected_version"])}
            for key in ("related_obligation_id", "ticket_source_id"):
                if key in raw:
                    row[key] = normalize_uuid(raw[key], nullable=True)
            refs.append(row)
        if len(sources) + len(settlements) + len(refs) > 100:
            invalid("一次纠错最多 100 个明确子操作。")
        for entries, key in ((sources, "item_id"), (settlements, "id"), (refs, "item_id")):
            if len({entry[key] for entry in entries}) != len(entries):
                invalid("纠错命令包含重复对象。")
        return {"sources": sources, "settlements": settlements, "refs": refs, "versions": versions}

    @staticmethod
    def _correction_roots(corrections):
        flows = set(corrections["versions"]["flows"])
        items = set(corrections["versions"]["items"])
        for correction in corrections["sources"]:
            items.add(correction["item_id"])
            if correction["action"] == "rebind_flow":
                flows.add(correction["new_flow_id"])
        for reference in corrections["refs"]:
            items.add(reference["item_id"])
            items.update(value for key, value in reference.items() if key in {"related_obligation_id", "ticket_source_id"} and value)
        for settlement in corrections["settlements"]:
            if settlement["action"] == "update":
                values = settlement["fields"]
                if values.get("flow_id"):
                    flows.add(normalize_uuid(values["flow_id"]))
                items.update(normalize_uuid(values[key]) for key in ("item_id", "source_item_id") if values.get(key))
        return flows, items

    def _apply_auxiliary_corrections(self, tx, corrections, graph):
        removed = 0
        versions = corrections["versions"]
        available_settlements = {s["id"] for s in graph["settlements"]}
        for correction in corrections["settlements"]:
            if correction["id"] not in available_settlements:
                invalid("分配不属于本次纠错关联范围。")
            old = tx.get("settlements", correction["id"])
            check_version(old, correction["expected_version"])
            if correction["action"] == "remove":
                for column, table, kind in (("item_id", "items", "items"), ("source_item_id", "items", "items"), ("flow_id", "flows", "flows")):
                    if old[column]:
                        self._require_version(tx.get(table, old[column]), versions, kind, tx)
                tx.delete("settlements", old["id"])
                self._bump_settlement_objects(tx, old)
                removed += 1
            else:
                proposed = self._settlement_values({**serialize({key: old[key] for key in SETTLEMENT_FIELDS | {"id"}}), **correction["fields"]})
                changes = {key: val for key, val in proposed.items() if key != "id" and old[key] != val}
                self._change_settlement(tx, old, changes, versions)
        for correction in corrections["refs"]:
            item = tx.get("items", correction["item_id"])
            original_version = item["version"] - int(("items", item["id"]) in tx._bumped)
            if original_version != correction["expected_version"]:
                conflict("被引用事项已经变化。", "cash_version_conflict")
            changes = {key: val for key, val in correction.items() if key in {"related_obligation_id", "ticket_source_id"}}
            for target_id in changes.values():
                if target_id:
                    self._require_version(tx.get("items", target_id), versions, "items", tx)
            new = {**item, **changes}
            if new["related_obligation_id"] and new["type"] != "expense" or new["ticket_source_id"] and new["type"] != "company_receivable":
                invalid("引用字段不适用于此事项类型。")
            self._validate_item(tx, new)
            tx.update("items", item["id"], changes)
        return removed

    def _delete_false_item(self, tx, item):
        graph = tx.relations(item_ids=[item["id"]])
        if graph["references"]:
            conflict("存在真实子事项引用，请在本次操作中明确解除或更正。")
        settlements = tx.settlements_for_items([item["id"]])
        if any(s["kind"] not in CASH_SETTLEMENTS for s in settlements):
            conflict("存在非现金事实，请明确更正或撤销后再删除。")
        for settlement in settlements:
            tx.delete("settlements", settlement["id"])
            self._bump_settlement_objects(tx, settlement)
        tx.remember_deleted("item", item["id"])
        tx.delete("items", item["id"])
        return len(settlements)

    def _apply_sources(self, tx, flow, corrections, *, deleting):
        owned = tx.rows("items", {"origin_flow_id": flow["id"]})
        actions = {entry["item_id"]: entry for entry in corrections["sources"]}
        if set(actions) - {item["id"] for item in owned}:
            invalid("来源纠错事项不属于此现金流水。")
        removed = 0
        for item in owned:
            action = actions.get(item["id"])
            if action:
                original_version = item["version"] - int(("items", item["id"]) in tx._bumped)
                if original_version != action["expected_version"]:
                    conflict("来源事项已变化。", "cash_version_conflict")
                if action["action"] == "correct_amount":
                    if deleting:
                        invalid("删除来源现金时不能保留指向它的金额更正事项。")
                    tx.update("items", item["id"], {"original_amount": action["original_amount"], "origin_date": flow["occurred_on"], "oa_project_id": flow["oa_project_id"], "project_name_snapshot": flow["project_name_snapshot"]})
                elif action["action"] == "keep_independent":
                    tx.update("items", item["id"], {"origin_flow_id": None, "origin_mode": None})
                elif action["action"] == "rebind_flow":
                    target = tx.get("flows", action["new_flow_id"])
                    check_version({**target, "version": target["version"] - int(("flows", target["id"]) in tx._bumped)}, action["expected_new_flow_version"])
                    if target["id"] == flow["id"]:
                        invalid("改绑必须选择另一笔真实来源现金。")
                    tx.update("items", item["id"], {"origin_flow_id": target["id"], "origin_mode": "linked"})
                    tx.update("flows", target["id"], {})
                    if target["task_occurrence_id"]:
                        tx.update("task_occurrences", target["task_occurrence_id"], {})
                else:
                    removed += self._delete_false_item(tx, item)
            elif deleting:
                if item["origin_mode"] == "linked":
                    tx.update("items", item["id"], {"origin_flow_id": None, "origin_mode": None})
                else:
                    later = [s for s in tx.settlements_for_items([item["id"]]) if s["flow_id"] != flow["id"]]
                    if later:
                        conflict("来源事项已有后续处理，请明确选择来源纠错方式。")
                    removed += self._delete_false_item(tx, item)
            elif item["origin_mode"] == "created":
                changes = {key: flow[source] for key, source in (("origin_date", "occurred_on"), ("oa_project_id", "oa_project_id"), ("project_name_snapshot", "project_name_snapshot")) if item[key] != flow[source]}
                if changes:
                    tx.update("items", item["id"], changes)
        return removed

    def update_flow(self, entity_id, payload, actor=None):
        entity_id = normalize_uuid(entity_id)
        value = fields(payload, FLOW_FIELDS | CORRECTION_FIELDS | {"expected_version"}, {"expected_version"})
        changes = {key: val for key, val in value.items() if key in FLOW_FIELDS}
        corrections = self._corrections(value)
        if not changes and not any(corrections[key] for key in ("sources", "settlements", "refs")):
            invalid("更正请求没有业务修改。")
        with self.repository.transaction(readonly=True) as tx:
            old = tx.get("flows", entity_id)
            check_version(old, value["expected_version"])
        proposed = self._flow_values({**serialize({key: old[key] for key in FLOW_FIELDS}), **changes})
        project = self._resolve_project(proposed["oa_project_id"]) if old["oa_project_id"] != proposed["oa_project_id"] else {"name": old["project_name_snapshot"], "selection_settings_version": None}
        proposed["project_name_snapshot"] = project["name"]
        extra_flows, extra_items = self._correction_roots(corrections)
        with self.repository.transaction() as tx:
            # New eligibility is checked before graph locks; unchanged metadata edits do not require OA.
            graph = self._lock_graph(tx, flow_ids=[entity_id], extra_flows=extra_flows, extra_items=extra_items, config_flows=[proposed], selection_version=project.get("selection_settings_version"))
            current = tx.get("flows", entity_id)
            check_version(current, value["expected_version"])
            actual = {key: val for key, val in proposed.items() if current[key] != val}
            if not actual and not any(corrections[key] for key in ("sources", "settlements", "refs")):
                return serialize({"flow": current, "version": current["version"], "changed": False, **self._affected(tx, graph)})
            new = {**current, **proposed}
            for key in ("from_account_id", "to_account_id"):
                if new[key]:
                    account = tx.get("accounts", new[key])
                    if new["occurred_on"] < account["opening_date"] or (new[key] != current[key] and not account["enabled"]):
                        conflict("账户起算日或启用状态不允许此项修改。")
            if new["category_id"]:
                category = tx.get("categories", new["category_id"])
                if category["group"] not in {new["kind"], "turnover"} or (new["category_id"] != current["category_id"] and not category["enabled"]):
                    conflict("分类与修改后的方向不匹配。")
            if current["task_occurrence_id"]:
                occurrence = tx.get("task_occurrences", current["task_occurrence_id"])
                if occurrence["template_values_snapshot"]["kind"] != new["kind"]:
                    conflict("现金方向与任务不一致。")
            if new["kind"] == "transfer" and (graph["owned"] or any(s["flow_id"] == entity_id for s in graph["settlements"])):
                conflict("有事项或分配的现金不能直接改为内部转账。")
            tx.update("flows", entity_id, actual)
            removed = self._apply_auxiliary_corrections(tx, corrections, graph)
            removed += self._apply_sources(tx, new, corrections, deleting=False)
            for settlement in tx.rows("settlements", {"flow_id": entity_id}):
                if settlement["occurred_on"] != new["occurred_on"]:
                    tx.update("settlements", settlement["id"], {"occurred_on": new["occurred_on"]})
                    self._bump_settlement_objects(tx, settlement)
            if current["task_occurrence_id"] and (actual or any(corrections[key] for key in ("sources", "settlements", "refs"))):
                tx.update("task_occurrences", current["task_occurrence_id"], {})
            self._validate_balances(tx, graph["item_ids"], graph["flow_ids"])
            row = tx.get("flows", entity_id)
            return serialize({"flow": row, "version": row["version"], "changed": True, **self._affected(tx, graph, removed_settlements=removed)})

    def delete_flow(self, entity_id, payload, actor=None):
        entity_id = normalize_uuid(entity_id)
        value = fields(payload, CORRECTION_FIELDS | {"expected_version"}, {"expected_version"})
        normalize_version(value["expected_version"])
        corrections = self._corrections(value)
        with self.repository.transaction() as tx:
            if tx.was_deleted("flow", entity_id):
                return {"id": entity_id, "deleted": True, "already_deleted": True, "affected_counts": {"items": 0, "tasks": 0, "settlements": 0}, "affected_items": [], "affected_tasks": [], "affected_preview_truncated": False}
            tx.get("flows", entity_id)
            extra_flows, extra_items = self._correction_roots(corrections)
            graph = self._lock_graph(tx, flow_ids=[entity_id], extra_flows=extra_flows, extra_items=extra_items)
            flow = tx.get("flows", entity_id)
            check_version(flow, value["expected_version"])
            removed = self._apply_auxiliary_corrections(tx, corrections, graph)
            removed += self._apply_sources(tx, flow, corrections, deleting=True)
            for settlement in tx.rows("settlements", {"flow_id": entity_id}):
                tx.delete("settlements", settlement["id"])
                self._bump_settlement_objects(tx, settlement)
                removed += 1
            tx.remember_deleted("flow", entity_id)
            tx.delete("flows", entity_id)
            if flow["task_occurrence_id"]:
                tx.update("task_occurrences", flow["task_occurrence_id"], {})
            self._validate_balances(tx, graph["item_ids"], graph["flow_ids"])
            return serialize({"id": entity_id, "deleted": True, "already_deleted": False, **self._affected(tx, graph, removed_settlements=removed)})

    def unlink_task(self, entity_id, payload, actor=None):
        entity_id = normalize_uuid(entity_id)
        value = fields(payload, {"expected_version", "expected_occurrence_version"}, {"expected_version", "expected_occurrence_version"})
        with self.repository.transaction() as tx:
            graph = self._lock_graph(tx, flow_ids=[entity_id])
            flow = tx.get("flows", entity_id)
            check_version(flow, value["expected_version"])
            if flow["source_kind"] != "manual" or flow["task_occurrence_id"] is None:
                conflict("只能解除手工流水的错误任务关联。")
            occurrence = tx.get("task_occurrences", flow["task_occurrence_id"])
            check_version(occurrence, value["expected_occurrence_version"])
            flow = tx.update("flows", entity_id, {"task_occurrence_id": None})
            occurrence = tx.update("task_occurrences", occurrence["id"], {})
            return serialize({"flow": flow, "occurrence": occurrence, "version": flow["version"], **self._affected(tx, graph)})

    def update_item(self, entity_id, payload, actor=None):
        entity_id = normalize_uuid(entity_id)
        value = fields(payload, ITEM_FIELDS | (CORRECTION_FIELDS - {"source_corrections"}) | {"expected_version"}, {"expected_version"})
        changes = {key: val for key, val in value.items() if key in ITEM_FIELDS}
        corrections = self._corrections(value)
        if not changes and not any(corrections[key] for key in ("settlements", "refs")):
            invalid("更正请求没有业务修改。")
        with self.repository.transaction(readonly=True) as tx:
            old = tx.get("items", entity_id)
            check_version(old, value["expected_version"])
        if "type" in changes and changes["type"] != old["type"]:
            invalid("事项业务类型不能直接改变。")
        item_input = serialize({key: old[key] for key in ITEM_FIELDS | {"id"}})
        if item_input["bill_month"]:
            item_input["bill_month"] = item_input["bill_month"][:7]
        proposed = self._item_values({**item_input, **changes})
        proposed.update(origin_flow_id=old["origin_flow_id"], origin_mode=old["origin_mode"])
        if old["origin_flow_id"] and any(proposed[key] != old[key] for key in ("original_amount", "origin_date", "oa_project_id", "is_opening", "obligation_direction")):
            conflict("来源事项的金额、日期或归属更正须通过对应现金流水。")
        project = self._resolve_project(proposed["oa_project_id"], historical=proposed["is_opening"]) if proposed["oa_project_id"] != old["oa_project_id"] else {"name": old["project_name_snapshot"], "selection_settings_version": None}
        proposed["project_name_snapshot"] = project["name"]
        extra_flows, extra_items = self._correction_roots(corrections)
        extra_items.update(key for key in (proposed["related_obligation_id"], proposed["ticket_source_id"]) if key)
        if old["origin_flow_id"]:
            extra_flows.add(old["origin_flow_id"])
        with self.repository.transaction() as tx:
            graph = self._lock_graph(tx, item_ids=[entity_id], extra_flows=extra_flows, extra_items=extra_items, config_items=[proposed], selection_version=None if proposed["is_opening"] else project.get("selection_settings_version"))
            current = tx.get("items", entity_id)
            check_version(current, value["expected_version"])
            for key in ("related_obligation_id", "ticket_source_id"):
                if proposed[key] and proposed[key] != current[key]:
                    self._require_version(tx.get("items", proposed[key]), corrections["versions"], "items", tx)
            actual = {key: val for key, val in proposed.items() if key != "id" and current[key] != val}
            if proposed["bill_label_id"] and proposed["bill_label_id"] != current["bill_label_id"] and not tx.get("bill_labels", proposed["bill_label_id"])["enabled"]:
                conflict("账单标识已经停用。")
            if not actual and not any(corrections[key] for key in ("settlements", "refs")):
                return serialize({"item": current, "version": current["version"], "changed": False, **self._affected(tx, graph)})
            removed = self._apply_auxiliary_corrections(tx, corrections, graph)
            item = tx.update("items", entity_id, actual)
            self._validate_item(tx, item)
            self._validate_balances(tx, graph["item_ids"], graph["flow_ids"])
            return serialize({"item": item, "version": item["version"], "changed": True, **self._affected(tx, graph, removed_settlements=removed)})

    def delete_item(self, entity_id, payload, actor=None):
        entity_id = normalize_uuid(entity_id)
        value = fields(payload, (CORRECTION_FIELDS - {"source_corrections"}) | {"expected_version"}, {"expected_version"})
        normalize_version(value["expected_version"])
        corrections = self._corrections(value)
        with self.repository.transaction() as tx:
            if tx.was_deleted("item", entity_id):
                return {"id": entity_id, "deleted": True, "already_deleted": True, "affected_counts": {"items": 0, "tasks": 0, "settlements": 0}, "affected_items": [], "affected_tasks": [], "affected_preview_truncated": False}
            tx.get("items", entity_id)
            extra_flows, extra_items = self._correction_roots(corrections)
            graph = self._lock_graph(tx, item_ids=[entity_id], extra_flows=extra_flows, extra_items=extra_items)
            item = tx.get("items", entity_id)
            check_version(item, value["expected_version"])
            if item["origin_flow_id"]:
                conflict("来源事项请从所属现金流水执行纠错。")
            removed = self._apply_auxiliary_corrections(tx, corrections, graph)
            removed += self._delete_false_item(tx, tx.get("items", entity_id))
            self._validate_balances(tx, graph["item_ids"], graph["flow_ids"])
            return serialize({"id": entity_id, "deleted": True, "already_deleted": False, **self._affected(tx, graph, removed_settlements=removed)})
