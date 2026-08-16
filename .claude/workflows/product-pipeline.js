export const meta = {
  name: 'product-pipeline',
  description: 'IDEA → 전략 → 기획 → PM → UX → UI → 아키텍처 → FE/BE 병렬 구현 → QA → 리뷰 → Fix/Done',
  whenToUse: '아이디어 한 줄에서 리뷰 통과까지 제품 전체를 한 번에 굴릴 때. args 로 아이디어 문자열을 넘긴다.',
  phases: [
    { title: 'Strategy',     detail: '시장·사용자·차별화 전략' },
    { title: 'Plan',         detail: '기능 목록과 MVP 경계' },
    { title: 'PRD',          detail: '유저스토리 + 수용 기준' },
    { title: 'UX',           detail: '정보구조·플로우·와이어프레임' },
    { title: 'UI',           detail: '디자인 토큰·컴포넌트 스펙' },
    { title: 'Architecture', detail: '스택·데이터모델·API 계약·티켓 분할' },
    { title: 'Build',        detail: '프론트/백엔드 병렬 구현' },
    { title: 'QA',           detail: '수용 기준 대비 실제 검증' },
    { title: 'Review',       detail: '품질·보안·계약 심사 및 판정' },
    { title: 'Fix',          detail: '리뷰 지적사항 수정 후 재검증' },
  ],
}

// ---------------------------------------------------------------- 입력
const idea = typeof args === 'string' ? args : args?.idea
if (!idea) throw new Error('아이디어를 args 로 넘겨라. 예: Workflow({name:"product-pipeline", args:"동네 러닝 크루 매칭 앱"})')

const MAX_FIX_ROUNDS = (typeof args === 'object' && args?.maxFixRounds) || 2
const DOCS = 'docs/pipeline'

// ---------------------------------------------------------------- 스키마
const STAGE = {
  type: 'object',
  properties: {
    docPath: { type: 'string', description: '작성한 문서 경로' },
    summary: { type: 'string', description: '다음 단계가 알아야 할 핵심 3~6문장' },
    decisions: { type: 'array', items: { type: 'string' }, description: '이 단계에서 확정한 결정들' },
    openQuestions: { type: 'array', items: { type: 'string' }, description: '사람이 답해야 할 것' },
  },
  required: ['docPath', 'summary'],
}

const BUILD = {
  type: 'object',
  properties: {
    area: { type: 'string', enum: ['frontend', 'backend'] },
    filesChanged: { type: 'array', items: { type: 'string' } },
    ticketsDone: { type: 'array', items: { type: 'string' } },
    verification: { type: 'string', description: '실제로 돌린 명령과 결과' },
    contractIssues: { type: 'array', items: { type: 'string' }, description: '계약이 틀렸다고 판단되는 지점(직접 고치지 않은 것)' },
    notes: { type: 'string' },
  },
  required: ['area', 'filesChanged', 'verification'],
}

const QA = {
  type: 'object',
  properties: {
    docPath: { type: 'string' },
    commandsRun: { type: 'array', items: { type: 'string' } },
    passed: { type: 'array', items: { type: 'string' } },
    defects: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          id: { type: 'string' },
          severity: { type: 'string', enum: ['P0', 'P1', 'P2', 'P3'] },
          area: { type: 'string', enum: ['frontend', 'backend', 'contract', 'unknown'] },
          summary: { type: 'string' },
          repro: { type: 'string' },
          location: { type: 'string' },
        },
        required: ['id', 'severity', 'area', 'summary'],
      },
    },
  },
  required: ['docPath', 'defects'],
}

const REVIEW = {
  type: 'object',
  properties: {
    docPath: { type: 'string' },
    verdict: { type: 'string', enum: ['pass', 'fix'] },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          severity: { type: 'string', enum: ['blocker', 'major', 'minor'] },
          area: { type: 'string', enum: ['frontend', 'backend', 'contract'] },
          location: { type: 'string' },
          problem: { type: 'string' },
          fix: { type: 'string' },
        },
        required: ['severity', 'area', 'problem', 'fix'],
      },
    },
    summary: { type: 'string' },
  },
  required: ['verdict', 'findings', 'summary'],
}

// ---------------------------------------------------------------- 1~6: 순차 사고 단계
// 각 단계는 문서를 파일로 남기고, 요약만 다음 단계로 넘긴다.
// 문서 전문을 컨텍스트로 나르지 않기 때문에 단계가 늘어나도 무너지지 않는다.
const chain = [
  { phase: 'Strategy',     type: 'product-strategist', doc: '01-strategy.md',     task: `아이디어: "${idea}"\n이 아이디어의 제품 전략을 세워라.` },
  { phase: 'Plan',         type: 'product-planner',    doc: '02-plan.md',         task: `전략 문서를 읽고 기능 목록과 MVP 경계를 정하라.` },
  { phase: 'PRD',          type: 'pm',                 doc: '03-prd.md',          task: `기획을 유저스토리(US-*)와 Given/When/Then 수용 기준을 갖춘 PRD로 만들어라.` },
  { phase: 'UX',           type: 'ux-designer',        doc: '04-ux.md',           task: `PRD를 정보구조·유저플로우·화면(SCR-*)·상태 정의로 설계하라.` },
  { phase: 'UI',           type: 'ui-designer',        doc: '05-ui.md',           task: `UX 구조에 디자인 토큰과 컴포넌트 스펙을 입혀라. 토큰은 실제 CSS 파일로 써라.` },
  { phase: 'Architecture', type: 'architect',          doc: '06-architecture.md', task: `스택·데이터모델·API 계약을 확정하고 FE-*/BE-* 티켓으로 분할하라. 공유 타입을 packages/shared 에 실제 파일로 써라. 프론트/백엔드 소유 경로가 절대 겹치지 않게 하라.` },
]

const context = []
for (const step of chain) {
  phase(step.phase)
  const prior = context.length
    ? `\n\n## 앞 단계 요약(참고용, 원문은 파일을 직접 읽어라)\n${context.map(c => `### ${c.phase}\n${c.summary}`).join('\n\n')}`
    : ''
  const result = await agent(
    `${step.task}\n\n산출물은 반드시 \`${DOCS}/${step.doc}\` 에 쓴다. 프로젝트 루트 기준 상대경로다.${prior}`,
    { agentType: step.type, label: step.phase.toLowerCase(), phase: step.phase, schema: STAGE },
  )
  if (!result) throw new Error(`${step.phase} 단계 실패 — 중단한다.`)
  context.push({ phase: step.phase, summary: result.summary })
  log(`✓ ${step.phase} → ${result.docPath}`)
  if (result.openQuestions?.length) log(`  ⚠︎ 열린 질문: ${result.openQuestions.join(' / ')}`)
}

// ---------------------------------------------------------------- 7: FE/BE 병렬
// 여기만 배리어가 필요하다. QA는 양쪽이 다 있어야 계약 정합성을 볼 수 있다.
phase('Build')
const built = (await parallel([
  () => agent(
    `아키텍처 문서의 FE-* 티켓을 모두 구현하라. apps/web(및 문서가 지정한 프론트 경로) 밖은 절대 수정하지 마라. 끝나면 빌드/타입체크/테스트를 실제로 실행해 결과를 보고하라.`,
    { agentType: 'frontend-dev', label: 'frontend', phase: 'Build', schema: BUILD },
  ),
  () => agent(
    `아키텍처 문서의 BE-* 티켓을 모두 구현하라. apps/api(및 문서가 지정한 백엔드 경로) 밖은 절대 수정하지 마라. 끝나면 빌드/타입체크/테스트를 실제로 실행해 결과를 보고하라.`,
    { agentType: 'backend-dev', label: 'backend', phase: 'Build', schema: BUILD },
  ),
])).filter(Boolean)

if (built.length < 2) log(`⚠︎ 구현 에이전트 ${2 - built.length}개가 결과를 내지 못했다. 남은 결과로 진행한다.`)
for (const b of built) {
  log(`✓ ${b.area}: ${b.filesChanged.length}개 파일 / ${b.verification}`)
  if (b.contractIssues?.length) log(`  ⚠︎ 계약 이슈(${b.area}): ${b.contractIssues.join(' / ')}`)
}

// ---------------------------------------------------------------- 8~10: QA → 리뷰 → Fix 루프
let round = 0
let qa = null
let review = null

while (true) {
  phase('QA')
  qa = await agent(
    `구현을 PRD 수용 기준 대비 검증하라. 빌드·타입체크·린트·테스트를 실제로 실행하고, 프론트가 호출하는 API와 백엔드 구현/공유 타입이 일치하는지 반드시 대조하라. 결함은 보고만 하고 코드는 고치지 마라. 결과는 ${DOCS}/07-qa.md 에 쓴다.`,
    { agentType: 'qa', label: round === 0 ? 'qa' : `qa-r${round}`, phase: 'QA', schema: QA },
  )
  const defects = qa?.defects ?? []
  log(`QA: 결함 ${defects.length}건 (P0 ${defects.filter(d => d.severity === 'P0').length})`)

  phase('Review')
  review = await agent(
    `QA 보고서와 실제 코드를 심사하라. 정확성·보안·계약 정합성·중복·접근성을 보고 판정을 내려라. 코드는 고치지 마라. 결과는 ${DOCS}/08-review.md 에 쓴다.` +
    (defects.length ? `\n\nQA 결함 요약:\n${defects.map(d => `- [${d.severity}/${d.area}] ${d.summary}`).join('\n')}` : ''),
    { agentType: 'reviewer', label: round === 0 ? 'review' : `review-r${round}`, phase: 'Review', schema: REVIEW },
  )

  const blocking = [
    ...(review?.findings ?? []).filter(f => f.severity !== 'minor'),
    ...defects.filter(d => d.severity === 'P0' || d.severity === 'P1').map(d => ({
      severity: 'blocker', area: d.area === 'contract' || d.area === 'unknown' ? 'backend' : d.area,
      location: d.location, problem: d.summary, fix: `QA 결함 ${d.id} 해결`,
    })),
  ]

  if (review?.verdict === 'pass' && blocking.length === 0) { log('✅ DONE — 리뷰 통과'); break }
  if (round >= MAX_FIX_ROUNDS) { log(`⛔️ Fix ${MAX_FIX_ROUNDS}회 후에도 미해결 ${blocking.length}건 — 사람 개입 필요`); break }

  round++
  phase('Fix')
  log(`🔁 Fix 라운드 ${round}: ${blocking.length}건 수정`)

  const byArea = { frontend: blocking.filter(f => f.area === 'frontend'), backend: blocking.filter(f => f.area !== 'frontend') }
  await parallel(
    Object.entries(byArea).filter(([, items]) => items.length).map(([area, items]) => () => agent(
      `아래 지적사항을 수정하라. 네 소유 경로 밖은 건드리지 마라. 수정 후 테스트를 다시 돌려 통과를 확인하라.\n\n` +
      items.map((f, i) => `${i + 1}. [${f.severity}] ${f.location ?? '위치 미상'}\n   문제: ${f.problem}\n   수정: ${f.fix}`).join('\n\n'),
      { agentType: area === 'frontend' ? 'frontend-dev' : 'backend-dev', label: `fix-${area}-r${round}`, phase: 'Fix', schema: BUILD },
    )),
  )
}

return {
  idea,
  verdict: review?.verdict ?? 'unknown',
  fixRounds: round,
  openDefects: (qa?.defects ?? []).filter(d => d.severity === 'P0' || d.severity === 'P1').length,
  blockers: (review?.findings ?? []).filter(f => f.severity === 'blocker').length,
  docs: `${DOCS}/01-strategy.md … 08-review.md`,
  summary: review?.summary,
}
