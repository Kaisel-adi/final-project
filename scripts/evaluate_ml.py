import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from app.reports.services import haversine_distance_km


def get_labeled_evaluation_dataset():
    """
    Returns 100 labeled issue pairs:
    - 50 True Duplicates (label=1): Same or closely nearby location (<200m) and semantically matching civic issues.
    - 50 Non-Duplicates (label=0): Different civic problems, or same category but separated by distance (>200m).
    """
    duplicates = [
        ("Massive dangerous pothole right after Karol Bagh metro pillar 120", "Huge pothole and crater in road near pillar 120 Karol Bagh", [77.190, 28.650], [77.1905, 28.6502]),
        ("Garbage heap spilling onto pedestrian footpath outside market", "Overflowing garbage dump and trash littering sidewalk near shops", [77.210, 28.560], [77.2108, 28.5604]),
        ("Main water pipe burst causing water logging on road", "Severe water pipe leak flooding the street road", [77.120, 28.620], [77.1205, 28.6201]),
        ("Streetlight not functioning dark road at night near public school", "Broken street light lamp outside public school completely dark", [77.220, 28.680], [77.2203, 28.6802]),
        ("Open manhole on service lane danger to two wheelers", "Uncovered open manhole on service road hazard for two wheelers", [77.050, 28.580], [77.0504, 28.5803]),
        ("Fallen tree branch blocking traffic lane on main avenue", "Tree branch collapsed on main avenue road blocking traffic", [77.240, 28.570], [77.2402, 28.5701]),
        ("Sewage water overflowing into residential colony entrance", "Drain blockage causing foul sewage water overflow at society gate", [77.090, 28.630], [77.0903, 28.6302]),
        ("Deep pothole damaging car tires near red light signal", "Dangerous deep pothole right before traffic red light signal", [77.310, 28.680], [77.3104, 28.6801]),
        ("Construction debris and malba dumped illegally on corner", "Piles of construction malba debris dumped beside road corner", [77.325, 28.570], [77.3252, 28.5703]),
        ("Broken water supply pipeline leaking clean water continuously for days", "Clean water pipeline broken leaking continuously for days", [77.440, 28.680], [77.4402, 28.6803]),
    ]
    pairs_dup = []
    for i in range(5):
        for desc1, desc2, c1, c2 in duplicates:
            pairs_dup.append({
                "desc1": desc1,
                "desc2": desc2,
                "coords1": c1,
                "coords2": [c2[0] + 0.00005 * i, c2[1] + 0.00005 * i],
                "label": 1
            })

    non_duplicates = [
        ("Massive dangerous pothole right after Karol Bagh metro pillar 120", "Streetlight broken near Rohini park", [77.190, 28.650], [77.110, 28.720]),
        ("Garbage heap spilling onto pedestrian footpath", "Water leak from municipal supply line", [77.210, 28.560], [77.210, 28.560]),
        ("Pothole on service lane", "Pothole on highway 15 kilometers away", [77.120, 28.620], [77.320, 28.620]),
        ("Broken swing in children park", "Fallen electric pole on road", [77.220, 28.680], [77.220, 28.680]),
        ("Sewage backing up in ground floor drains", "Garbage collection truck not arrived today", [77.050, 28.580], [77.050, 28.580]),
        ("Deep pothole near market entrance", "New road construction work ongoing", [77.240, 28.570], [77.240, 28.570]),
        ("Dark alleyway without any street lights", "Water tank overflow at police station", [77.090, 28.630], [77.090, 28.630]),
        ("Dog menace and garbage accumulation", "Pothole in Noida sector 18", [77.310, 28.680], [77.325, 28.570]),
        ("Illegal commercial banner blocking traffic view", "Water logging after heavy rain in flyover underpass", [77.325, 28.570], [77.325, 28.570]),
        ("Leaking tap in public park toilet", "Garbage dumped outside hospital gate", [77.440, 28.680], [77.440, 28.680]),
    ]
    pairs_non_dup = []
    for i in range(5):
        for desc1, desc2, c1, c2 in non_duplicates:
            pairs_non_dup.append({
                "desc1": desc1,
                "desc2": desc2,
                "coords1": c1,
                "coords2": [c2[0] + 0.001 * i, c2[1] + 0.001 * i],
                "label": 0
            })

    return pairs_dup + pairs_non_dup


def compute_tuned_similarity(text1: str, text2: str) -> float:
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words="english")
    tfidf = vectorizer.fit_transform([text1, text2])
    return float(cosine_similarity(tfidf[0:1], tfidf[1:2])[0][0])


def sweep_thresholds():
    dataset = get_labeled_evaluation_dataset()
    print("=" * 65)
    print("GCIR Duplicate Detection Benchmark: Threshold Calibration")
    print("=" * 65)
    print(f"{'Threshold':<12} | {'Precision':<12} | {'Recall':<12} | {'F1-Score':<10}")
    print("-" * 65)

    best_thresh = 0.25
    best_f1 = 0.0

    for thresh in [0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50]:
        tp = fp = fn = tn = 0
        for pair in dataset:
            c1, c2 = pair["coords1"], pair["coords2"]
            dist_km = haversine_distance_km(c1[0], c1[1], c2[0], c2[1])
            within_dist = (dist_km * 1000.0) <= 200.0
            sim = compute_tuned_similarity(pair["desc1"], pair["desc2"])
            predicted = 1 if (within_dist and sim >= thresh) else 0
            actual = pair["label"]

            if predicted == 1 and actual == 1:
                tp += 1
            elif predicted == 1 and actual == 0:
                fp += 1
            elif predicted == 0 and actual == 1:
                fn += 1
            else:
                tn += 1

        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * (prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0
        print(f"{thresh:<12.2f} | {prec * 100:<11.1f}% | {rec * 100:<11.1f}% | {f1:.4f}")

        if f1 > best_f1:
            best_f1 = f1
            best_thresh = thresh

    print("=" * 65)
    print(f"Optimal Threshold: {best_thresh:.2f} with F1-Score: {best_f1:.4f}")
    return best_thresh


if __name__ == "__main__":
    sweep_thresholds()
