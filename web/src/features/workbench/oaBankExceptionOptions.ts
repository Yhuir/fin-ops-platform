export type OaBankExceptionMode = "oa_only" | "bank_only" | "oa_bank" | "invalid";

export type OaBankExceptionOption = {
  code: string;
  label: string;
  flow: "exception" | "split_merge" | "settle_as_pair";
};

export const OA_BANK_EXCEPTION_OPTIONS = {
  oaMissingBank: {
    code: "oa_missing_bank",
    label: "无对应流水（还没付钱）",
    flow: "exception",
  },
  bankMissingOaFee: {
    code: "bank_missing_oa_fee",
    label: "无对应OA（补手续费）",
    flow: "exception",
  },
  bankMissingOaLoan: {
    code: "bank_missing_oa_loan",
    label: "无对应OA（补贷款）",
    flow: "exception",
  },
  bankMissingOaInterest: {
    code: "bank_missing_oa_interest",
    label: "无对应OA（补利息）",
    flow: "exception",
  },
  bankMissingOaMisc: {
    code: "bank_missing_oa_misc",
    label: "无对应OA（补电信托收薪资保险往来款标灰）",
    flow: "exception",
  },
  oaBankAmountMismatch: {
    code: "oa_bank_amount_mismatch",
    label: "金额不一致，继续异常",
    flow: "exception",
  },
  oaOneToManyBank: {
    code: "oa_one_to_many_bank",
    label: "一个OA多个流水",
    flow: "split_merge",
  },
  oaManyToOneBank: {
    code: "oa_many_to_one_bank",
    label: "多个OA一笔流水",
    flow: "split_merge",
  },
  personalAdvanceRepaymentSettlement: {
    code: "personal_advance_repayment_settlement",
    label: "还清个人暂借款",
    flow: "settle_as_pair",
  },
} satisfies Record<string, OaBankExceptionOption>;

export function buildOaBankExceptionOptions({
  oaCount,
  bankCount,
  invoiceCount,
}: {
  oaCount: number;
  bankCount: number;
  invoiceCount: number;
}): { mode: OaBankExceptionMode; options: OaBankExceptionOption[] } {
  if (invoiceCount > 0 || (oaCount === 0 && bankCount === 0)) {
    return { mode: "invalid", options: [] };
  }

  if (oaCount > 0 && bankCount === 0) {
    return {
      mode: "oa_only",
      options: [OA_BANK_EXCEPTION_OPTIONS.oaMissingBank],
    };
  }

  if (oaCount === 0 && bankCount > 0) {
    return {
      mode: "bank_only",
      options: [
        OA_BANK_EXCEPTION_OPTIONS.bankMissingOaFee,
        OA_BANK_EXCEPTION_OPTIONS.bankMissingOaLoan,
        OA_BANK_EXCEPTION_OPTIONS.bankMissingOaInterest,
        OA_BANK_EXCEPTION_OPTIONS.bankMissingOaMisc,
      ],
    };
  }

  const options: OaBankExceptionOption[] = [
    OA_BANK_EXCEPTION_OPTIONS.oaBankAmountMismatch,
    OA_BANK_EXCEPTION_OPTIONS.personalAdvanceRepaymentSettlement,
  ];
  if (oaCount === 1 && bankCount > 1) {
    options.push(OA_BANK_EXCEPTION_OPTIONS.oaOneToManyBank);
  }
  if (oaCount > 1 && bankCount === 1) {
    options.push(OA_BANK_EXCEPTION_OPTIONS.oaManyToOneBank);
  }
  return {
    mode: "oa_bank",
    options,
  };
}
