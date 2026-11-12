"""Use current settings until publication, then preserve the grading standard."""

from open_webui.models.education import (
    AssignmentModel,
    AssignmentScoringConfig,
    SubmissionReviewModel,
)


def assignment_scoring(assignment: AssignmentModel) -> AssignmentScoringConfig:
    return AssignmentScoringConfig(
        scoring_mode=assignment.scoring_mode,
        score_max=assignment.score_max,
        rubric_schema=assignment.rubric_schema,
    )


def review_scoring_assignment(assignment: AssignmentModel, review: SubmissionReviewModel | None) -> AssignmentModel:
    if review is None or review.review_status == 'pending':
        return assignment
    return assignment.model_copy(
        update={
            'scoring_mode': review.scoring_config.scoring_mode,
            'score_max': review.scoring_config.score_max,
            'rubric_schema': review.scoring_config.rubric_schema,
        }
    )


def review_for_scoring(
    review: SubmissionReviewModel | None, assignment: AssignmentModel
) -> SubmissionReviewModel | None:
    if review and review.review_status == 'pending' and review.scoring_config != assignment_scoring(assignment):
        return review.model_copy(update={'score': None, 'rubric_scores': None})
    return review
