---
name: asterdesk-it-policy
slug: asterdesk-it-policy
version: 1.0.0
description: "回答虚构企业的软件权限申请材料问题，并给出政策文档、版本和章节定位。"
allowed-tools: []
metadata:
  permissions:
    - knowledge:it-policy:read
  visibility: tenant
---

# AsterDesk 示例 IT 政策

仅当用户询问软件权限申请要求时使用本 Skill。以下内容是虚构测试资料，不对应真实企业。

## 文档身份

- 文档 ID：`AsterDesk-IT-POL-001`
- 标题：软件访问与权限申请政策
- 版本：`1.0`
- 生效日期：`2026-09-01`

## 第 3 节：申请材料

申请软件权限时必须提供：

1. 申请人姓名和所属部门；
2. 软件名称、版本以及所需权限范围；
3. 使用设备的资产编号和操作系统；
4. 业务用途与预计使用期限；
5. 直属主管确认；
6. 涉及的数据分类，以及是否需要导出或对外共享数据的说明。

管理员权限、敏感数据或对外共享场景还需要信息安全复核。购买许可证属于采购流程，不得把“已提交权限申请”描述为“已完成采购”。

回答必须引用：`[AsterDesk-IT-POL-001 v1.0, §3 申请材料]`。不得补充本文没有规定的真实公司流程。
