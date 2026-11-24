import time
import random

def run_benchmark(NUM_STUDENTS):
    NUM_COURSES = 100
    # Scale payments proportionally to students
    NUM_PAYMENTS = NUM_STUDENTS * 2 
    
    student_ids = [i for i in range(1, NUM_STUDENTS + 1)]
    course_ids = [i for i in range(101, 101 + NUM_COURSES)]
    payment_ids = [i for i in range(1000, 1000 + NUM_PAYMENTS)]

    # ==========================================
    # 1. RELATIONAL DB SETUP
    # ==========================================
    rel_enrollments_table = []
    for sid in student_ids:
        for _ in range(3):
            cid = random.choice(course_ids)
            rel_enrollments_table.append({"student_id": sid, "course_id": cid})

    rel_payments_table = {}
    for pid in payment_ids:
        sid = random.choice(student_ids)
        pending_fee = random.choice([0, 5000, 10000, 20000])
        rel_payments_table[pid] = {"student_id": sid, "pending_fee": pending_fee}

    # ==========================================
    # 2. KNOWLEDGE GRAPH SETUP
    # ==========================================
    kg_students = {sid: {"courses": [], "payments": []} for sid in student_ids}
    kg_courses = {cid: {"students": []} for cid in course_ids}
    kg_payments = {pid: {"pending_fee": 0, "student_id": None} for pid in payment_ids}

    for enroll in rel_enrollments_table:
        sid = enroll["student_id"]
        cid = enroll["course_id"]
        kg_students[sid]["courses"].append(cid)
        kg_courses[cid]["students"].append(sid)

    for pid, data in rel_payments_table.items():
        sid = data["student_id"]
        kg_payments[pid]["pending_fee"] = data["pending_fee"]
        kg_payments[pid]["student_id"] = sid
        kg_students[sid]["payments"].append(pid)

    TARGET_STUDENT = NUM_STUDENTS // 2

    # ==========================================
    # 3. RELATIONAL QUERY (JOINs)
    # ==========================================
    start_time = time.perf_counter()
    rel_operations = 0

    target_courses = []
    for row in rel_enrollments_table:
        rel_operations += 1
        if row["student_id"] == TARGET_STUDENT:
            target_courses.append(row["course_id"])

    other_students = set()
    for row in rel_enrollments_table:
        rel_operations += 1
        if row["course_id"] in target_courses:
            other_students.add(row["student_id"])

    rel_results = 0
    for pid, p_data in rel_payments_table.items():
        rel_operations += 1
        if p_data["student_id"] in other_students:
            if p_data["pending_fee"] > 0:
                rel_results += 1

    rel_time = time.perf_counter() - start_time

    # ==========================================
    # 4. KG QUERY (Traversals)
    # ==========================================
    start_time = time.perf_counter()
    kg_operations = 0

    target_courses_kg = kg_students[TARGET_STUDENT]["courses"]
    kg_operations += 1

    other_students_kg = set()
    for cid in target_courses_kg:
        kg_operations += 1
        for sid in kg_courses[cid]["students"]:
            kg_operations += 1
            other_students_kg.add(sid)

    kg_results = 0
    for sid in other_students_kg:
        kg_operations += 1
        for pid in kg_students[sid]["payments"]:
            kg_operations += 1
            if kg_payments[pid]["pending_fee"] > 0:
                kg_results += 1

    kg_time = time.perf_counter() - start_time

    # Return stats
    return {
        "size": NUM_STUDENTS,
        "rel_ops": rel_operations,
        "kg_ops": kg_operations,
        "rel_time": rel_time,
        "kg_time": kg_time,
        "results": rel_results
    }

# ==========================================
# 5. RUN THE BENCHMARK ACROSS SIZES
# ==========================================
print("Running Benchmarks... (This may take a few seconds)\n")

# Define the sizes we want to test
test_sizes = [1000, 10000, 50000, 100000]
results_data = []

for size in test_sizes:
    print(f"Testing with {size} students...")
    res = run_benchmark(size)
    results_data.append(res)

# ==========================================
# 6. PRINT THE RESULTS IN A TABLE
# ==========================================
print("\n" + "="*90)
print(f"{'STUDENTS':<10} | {'RELATIONAL OPS':<15} | {'KG OPS':<10} | {'REL TIME (s)':<12} | {'KG TIME (s)':<12} | {'SPEEDUP'}")
print("="*90)

for r in results_data:
    speedup = r['rel_time'] / r['kg_time'] if r['kg_time'] > 0 else 0
    print(f"{r['size']:<10} | {r['rel_ops']:<15} | {r['kg_ops']:<10} | {r['rel_time']:<12.6f} | {r['kg_time']:<12.6f} | {speedup:.1f}x")

print("="*90)
print("Notice how the Relational Operations grow massively, while KG Operations scale mostly with the local neighborhood (constant).")