# 파이프라인 문서

`.claude/agents/*`가 읽고 쓰는 경로입니다. 에이전트별로 담당 파일이 정해져 있습니다.

| 단계 | 파일 | 담당 에이전트 | 상태 |
|---|---|---|---|
| 1 | [01-strategy.md](01-strategy.md) | product-strategist | 작성됨 |
| 2 | [02-plan.md](02-plan.md) | product-planner | 작성됨 |
| 3 | [03-prd.md](03-prd.md) | pm | 작성됨 |
| 4 | [04-ux.md](04-ux.md) | ux-designer | 작성됨 |
| 5 | [05-ui.md](05-ui.md) + [design-tokens.css](design-tokens.css) | ui-designer | 작성됨 |
| 6 | [06-architecture.md](06-architecture.md) + `packages/shared/` | architect | 작성됨 |
| 7 | `07-qa.md` | qa | 구현 후 생성 |
| 8 | `08-review.md` | reviewer | QA 후 생성 |

## 설계 문서와의 관계

`docs/` 최상위의 문서가 **정본**이고, 여기 파이프라인 문서는 그것을
에이전트가 소비할 수 있는 형식으로 정리한 것입니다.

| 파이프라인 | 정본 |
|---|---|
| 01-strategy | (신규 — 고객·수익 모델 결정) |
| 02-plan | (신규 — 기능 목록과 우선순위) |
| 03-prd | [../01-product-spec.md](../01-product-spec.md) |
| 04-ux | ../01-product-spec.md + [../04-venue-layout.md](../04-venue-layout.md) + [../05-booth-experience.md](../05-booth-experience.md) |
| 05-ui | [../06-charts.md](../06-charts.md) + 디자인 시스템 아티팩트 |
| 06-architecture | [../02-data-model.md](../02-data-model.md) + [../03-api-contract.md](../03-api-contract.md) |

**상세가 필요하면 정본을 보세요.** 파이프라인 문서는 MVP 관문 범위로 압축돼 있습니다.
전체 범위(행사장 설계, 부스 QR 체험, 보상 캠페인, 최종 기획서, 사후 리포트 전체)는
정본 문서에 그대로 있으며 v1에서 이어집니다.

## ID 체계

뒷 단계가 앞 단계를 이 ID로 참조합니다.

```
F-*   기능        02-plan.md
US-*  유저스토리   03-prd.md
SCR-* 화면        04-ux.md
FE-*  프론트 티켓  06-architecture.md
BE-*  백엔드 티켓  06-architecture.md
```

## 소유 경계

| 경로 | 소유 | 다른 쪽 |
|---|---|---|
| `apps/api/**` | 백엔드 | 읽기만 |
| `apps/web/**` | 프론트 | 읽기만 |
| `packages/shared/**` | **백엔드** | 프론트는 읽기만 |

프론트가 계약이 틀렸다고 판단하면 직접 고치지 말고 **"계약 이슈"로 보고**합니다.
양쪽이 같은 파일을 고치면 병렬 실행에서 충돌합니다.

## 실행 전 확인

`BE-0`(스키마 + `packages/shared` 생성)이 **유일한 직렬 선행 작업**입니다.
그게 끝나야 프론트가 계약대로 목을 세우고 병렬로 출발할 수 있습니다.
