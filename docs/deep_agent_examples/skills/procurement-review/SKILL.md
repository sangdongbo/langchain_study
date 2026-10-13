---
name: procurement-review
description: Review enterprise purchases using deterministic evidence and an approval-safe procedure
---

# Procurement Review

1. Calculate the total with `calculate_total`; never do money arithmetic from memory.
2. Check inventory, department budget, and supplier risk.
3. Separate blocking findings from recommendations.
4. Cite the exact tool result behind every amount and risk.
5. Never claim a review was published unless `publish_review` returned success.
6. Answer in Chinese with: request summary, evidence, risks, and recommendation.
