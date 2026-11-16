"""확인용 브랜치 전용: 수집 결과 파일을 로그로 내보낸다. main 에는 올리지 않는다."""
import base64, gzip
import common
for path in sorted(common.DATA_DIR.glob("*.json")):
    raw = path.read_bytes()
    packed = base64.b64encode(gzip.compress(raw, 9)).decode()
    print(f"@@FILE {path.name} {len(raw)}")
    for i in range(0, len(packed), 3000):
        print("@@DATA " + packed[i:i + 3000])
    print("@@END")
