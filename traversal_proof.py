import time
import random

# ==========================================
# 0. SETUP: Generate Dummy Data
# ==========================================
NUM_STUDENTS = 50000
NUM_PAYMENTS = 100000
TARGET_STUDENT = 25000 # The student we are searching for

print("Generating data...")
student_ids = [i for i in range(1, NUM_STUDENTS + 1)]
payment_ids = [i for i in range(1000, 1000 + NUM_PAYMENTS)]

# Randomly assign payments to students
payment_data = []
for pid in payment_ids:
    sid = random.choice(student_ids)
    payment_data.append({"payment_id": pid, "student_id": sid, "amount": 500})

# ==========================================
# 1. RELATIONAL DATABASE MODEL
# ==========================================
print("\n--- RELATIONAL DB REVERSE TRAVERSAL ---")
# In RDBMS, the Payment table holds the Foreign Key (student_id).
# The Student table has NO knowledge of its payments.
rel_payment_table = payment_data

start_time = time.perf_counter()
rel_operations = 0
rel_results = []

# THE BOTTLENECK: To find payments for a student, we MUST scan the whole table
for payment in rel_payment_table:
    rel_operations += 1  # Count every row we inspect
    if payment["student_id"] == TARGET_STUDENT:
        rel_results.append(payment["payment_id"])

rel_time = time.perf_counter() - start_time

print(f"Time Taken: {rel_time:.6f} seconds")
print(f"Operations (Rows Scanned): {rel_operations}")
print(f"Payments Found: {len(rel_results)}")


# ==========================================
# 2. KNOWLEDGE GRAPH MODEL
# ==========================================
print("\n--- KNOWLEDGE GRAPH REVERSE TRAVERSAL ---")
# In a KG, the Student Node physically stores pointers to its Payments (Edges).
kg_students = {sid: {"payments": []} for sid in student_ids}

# Build the edges (Index-Free Adjacency)
for payment in payment_data:
    sid = payment["student_id"]
    pid = payment["payment_id"]
    # We attach the pointer directly to the student
    kg_students[sid]["payments"].append(pid)

start_time = time.perf_counter()
kg_operations = 0

# THE SOLUTION: We just read the student's direct pointer list. No scanning.
kg_results = kg_students[TARGET_STUDENT]["payments"]
kg_operations += 1  # Count the single dictionary lookup

kg_time = time.perf_counter() - start_time

print(f"Time Taken: {kg_time:.6f} seconds")
print(f"Operations (Edge Traversals): {kg_operations}")
print(f"Payments Found: {len(kg_results)}")

# ==========================================
# 3. THE PROOF
# ==========================================
print("\n" + "="*50)
print("FINAL PROOF")
print("="*50)
if kg_time > 0:
    speedup = rel_time / kg_time
    print(f"The Knowledge Graph was {speedup:.1f}x faster.")
print(f"The Relational DB performed {rel_operations} operations.")
print(f"The Knowledge Graph performed {kg_operations} operation.")
print(f"Efficiency Gain: {rel_operations / kg_operations:.0f}x fewer operations in the KG.")

