---
description: 아이디어 한 줄을 전략→기획→PM→UX→UI→아키텍처→FE/BE→QA→리뷰까지 전체 파이프라인으로 굴린다
argument-hint: <아이디어 한 줄>
---

사용자가 `$ARGUMENTS` 를 아이디어로 주고 전체 제품 파이프라인 실행을 요청했다.

Workflow 도구를 다음과 같이 호출하라:

```
Workflow({ name: "product-pipeline", args: "$ARGUMENTS" })
```

- `$ARGUMENTS` 가 비어 있으면 실행하지 말고 아이디어 한 줄을 먼저 물어라.
- 워크플로는 백그라운드로 돌고 완료 시 알림이 온다. 그 사이 사용자를 기다리게 하지 말고, 진행 상황은 `/workflows` 에서 볼 수 있다고 알려라.
- 완료되면 판정(verdict), Fix 라운드 수, 남은 결함, `docs/pipeline/` 산출물 위치를 요약해 보고하라.
