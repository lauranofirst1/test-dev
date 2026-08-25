/** 화면 바닥의 푸터.
 *
 * ## 무엇이 여기 있어야 하나
 *
 * **출처 표기가 여기 있어야 합니다.** 한국관광공사 데이터를 쓰는 이상 출처는
 * 화면에 반드시 있어야 하는데, 예전에는 상단바에 있었습니다. 상단바는 축제
 * 전환·검색·현장 화면·계정이 다투는 자리라 출처가 그 사이에 끼어 있으면
 * 셋 다 좁아지고, 정작 출처는 아무도 안 봅니다. 푸터는 항상 있고 아무와도
 * 다투지 않는 자리입니다.
 *
 * ## 관객 화면에는 다르게 나간다
 *
 * 관객 화면 바닥에는 하단 탭이 붙박여 있습니다. 그 위에 푸터를 또 얹으면
 * 엄지가 닿는 자리를 두 겹으로 막습니다. 그래서 관객 쪽은 링크 없이 출처
 * 한 줄만 냅니다 — 관객에게 «데이터 출처 안내» 같은 링크는 할 일이 아닙니다.
 *
 * ## 링크를 늘리지 않는다
 *
 * 흔한 푸터에는 회사 소개·이용약관·문의가 줄줄이 붙습니다. 이 제품에는
 * 그런 페이지가 없고, 없는 곳으로 가는 링크는 죽은 링크입니다.
 */

export function AppFooter({ variant = 'console' }: { variant?: 'console' | 'audience' }) {
  const year = new Date().getFullYear();

  if (variant === 'audience') {
    return (
      <footer className="afoot afoot--audience">
        <p>출처: ⓒ한국관광공사</p>
      </footer>
    );
  }

  return (
    <footer className="afoot">
      <div className="afoot__in">
        <p className="afoot__brand">
          <strong>FestaFlow</strong>
          <span>축제를 진단하고, 현장을 재고, 다음 기획을 고칩니다</span>
        </p>

        <div className="afoot__meta">
          {/* 출처는 조건부로 빼지 않는다. 빠진 화면에서 이 숫자들이
              어디서 왔는지 알 수 없어진다. */}
          <p>
            관광 데이터 출처: <strong>ⓒ한국관광공사</strong>
          </p>
          <p className="tabular">© {year} FestaFlow</p>
        </div>
      </div>
    </footer>
  );
}
