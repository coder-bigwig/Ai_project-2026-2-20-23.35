import os
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.session import get_db
from ...services.submission_service import build_submission_service


def _get_main_module():
    from ... import main
    return main


main = _get_main_module()
router = APIRouter()


async def start_experiment(
    experiment_id: str,
    student_id: str,
    db: Optional[AsyncSession] = Depends(get_db),
):
    service = build_submission_service(main_module=main, db=db)
    return await service.start_experiment(experiment_id=experiment_id, student_id=student_id)


async def submit_experiment(
    student_exp_id: str,
    submission: main.SubmitExperimentRequest,
    db: Optional[AsyncSession] = Depends(get_db),
):
    service = build_submission_service(main_module=main, db=db)
    return await service.submit_experiment(student_exp_id=student_exp_id, submission=submission)


async def upload_submission_pdf(
    student_exp_id: str,
    file: UploadFile = File(...),
    db: Optional[AsyncSession] = Depends(get_db),
):
    service = build_submission_service(main_module=main, db=db)
    return await service.upload_submission_pdf(student_exp_id=student_exp_id, file=file)


async def list_submission_pdfs(
    student_exp_id: str,
    db: Optional[AsyncSession] = Depends(get_db),
):
    service = build_submission_service(main_module=main, db=db)
    return await service.list_submission_pdfs(student_exp_id=student_exp_id)


async def mark_submission_pdf_viewed(
    pdf_id: str,
    teacher_username: str,
    db: Optional[AsyncSession] = Depends(get_db),
):
    service = build_submission_service(main_module=main, db=db)
    return await service.mark_submission_pdf_viewed(pdf_id=pdf_id, teacher_username=teacher_username)


async def add_submission_pdf_annotation(
    pdf_id: str,
    payload: main.PDFAnnotationCreateRequest,
    db: Optional[AsyncSession] = Depends(get_db),
):
    service = build_submission_service(main_module=main, db=db)
    return await service.add_submission_pdf_annotation(pdf_id=pdf_id, payload=payload)


async def get_student_experiments(
    student_id: str,
    db: Optional[AsyncSession] = Depends(get_db),
):
    service = build_submission_service(main_module=main, db=db)
    return await service.get_student_experiments(student_id=student_id)


async def get_student_experiment_detail(
    student_exp_id: str,
    db: Optional[AsyncSession] = Depends(get_db),
):
    service = build_submission_service(main_module=main, db=db)
    return await service.get_student_experiment_detail(student_exp_id=student_exp_id)


async def download_submission_pdf(
    pdf_id: str,
    teacher_username: Optional[str] = None,
    db: Optional[AsyncSession] = Depends(get_db),
):
    service = build_submission_service(main_module=main, db=db)
    record = await service.download_submission_pdf(pdf_id=pdf_id, teacher_username=teacher_username)
    file_path = getattr(record, "file_path", "")
    filename = getattr(record, "filename", "document.pdf")
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="PDF 文件不存在")
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/pdf",
        content_disposition_type="inline",
    )


async def get_experiment_submissions(
    experiment_id: str,
    db: Optional[AsyncSession] = Depends(get_db),
):
    service = build_submission_service(main_module=main, db=db)
    return await service.get_experiment_submissions(experiment_id=experiment_id)


async def grade_experiment(
    student_exp_id: str,
    score: float,
    comment: Optional[str] = None,
    teacher_username: Optional[str] = None,
    db: Optional[AsyncSession] = Depends(get_db),
):
    service = build_submission_service(main_module=main, db=db)
    return await service.grade_experiment(
        student_exp_id=student_exp_id,
        score=score,
        comment=comment,
        teacher_username=teacher_username,
    )


router.add_api_route("/api/student-experiments/start/{experiment_id}", start_experiment, methods=["POST"])
router.add_api_route("/api/student-experiments/{student_exp_id}/submit", submit_experiment, methods=["POST"])
router.add_api_route("/api/student-experiments/{student_exp_id}/pdf", upload_submission_pdf, methods=["POST"])
router.add_api_route("/api/student-experiments/{student_exp_id}/pdfs", list_submission_pdfs, methods=["GET"])
router.add_api_route("/api/student-submissions/{pdf_id}/view", mark_submission_pdf_viewed, methods=["POST"])
router.add_api_route("/api/student-submissions/{pdf_id}/annotations", add_submission_pdf_annotation, methods=["POST"])
router.add_api_route("/api/student-experiments/my-experiments/{student_id}", get_student_experiments, methods=["GET"])
router.add_api_route("/api/student-experiments/{student_exp_id}", get_student_experiment_detail, methods=["GET"])
router.add_api_route("/api/student-submissions/{pdf_id}/download", download_submission_pdf, methods=["GET"])
router.add_api_route("/api/teacher/experiments/{experiment_id}/submissions", get_experiment_submissions, methods=["GET"])
router.add_api_route("/api/teacher/grade/{student_exp_id}", grade_experiment, methods=["POST"])
