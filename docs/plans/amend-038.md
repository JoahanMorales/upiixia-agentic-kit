## UAK-038 · Registered reviewers get the review work first

- **Type:** bug
- **Priority:** P2
- **Estimate:** 1.5 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/lib/status.sh, kit/.uak/bin/lib/wait.sh, kit/.uak/bin/uak-coordination, kit/.uak/bin/uak, kit/.uak/tests/test_reviewer_next.py
- **Acceptance:**
  - for an identity registered as reviewer (or with no live claim and reviews pending), `uak next` offers every REVIEW task it may review before any coding task; `uak wait --for message` also wakes when a task enters REVIEW that it may review
  - `uak status ID --summary` works like `status --task ID --summary`
  - why (DevDay): a review-only Codex agent missed a REVIEW task because next offered coding work and wait did not wake it; Codex hit "--summary needs --task ID" 3 times in deus
- **Tests:** reviewer_next_offers_review_first, wait_wakes_on_new_review_work, status_id_summary_works
- **Verify:** `python3 kit/.uak/tests/test_reviewer_next.py`
- **Next step:** the candidate order of coord_next in kit/.uak/bin/uak-coordination

