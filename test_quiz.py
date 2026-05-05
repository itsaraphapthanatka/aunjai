import logging
from quiz_pipeline import run_quiz_pipeline
from quiz_store import get_quiz_from_pinecone
from highlight_pipeline import extract_video_id

import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")

test_url = "https://www.youtube.com/watch?v=S8gT18F5i44" # A relatively short informative video 

print("1. RUNNING PIPELINE")
result = run_quiz_pipeline(test_url)

print("2. PIPELINE RESULT:")
print(result)

if result["status"] == "success":
    print("3. WAITING 5 SECONDS FOR PINECONE INDEXING")
    time.sleep(5)
    
    video_id = extract_video_id(test_url)
    print(f"4. FETCHING FROM PINECONE (video_id: {video_id})")
    saved_quiz = get_quiz_from_pinecone(video_id)
    
    print(f"5. FOUND {len(saved_quiz)} QUESTIONS IN PINECONE:")
    for i, q in enumerate(saved_quiz):
        print(f"Q{i+1}: {q.get('question')} (Ans: {q.get('answer')})")
else:
    print("PIPELINE FAILED.")
