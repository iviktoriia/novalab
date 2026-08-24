
from sqlalchemy import (
    Column, Integer, String, Text, Float, DateTime, ForeignKey, Boolean,
    Enum, CheckConstraint, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from app.core.database import Base

class RegistrationMethod(str, enum.Enum):
    """Registrationmethod."""
    AUTO = "auto"
    SELF = "self"

class SubmissionStatus(str, enum.Enum):
    """Submissionstatus."""
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    REVISION = "revision"
    REJECTED = "rejected"

class AttestationType(str, enum.Enum):
    """Вид итоговой аттестации по дисциплине."""
    EXAM = "exam"
    DIF_CREDIT = "dif_credit"
    CREDIT = "credit"
    PROJECT = "project"
    OTHER = "other"
    NONE = "none"

class AnalysisStatus(str, enum.Enum):
    """Analysisstatus."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"

class MaterialType(str, enum.Enum):
    """Materialtype."""
    LECTURE = "lecture"
    PRACTICAL = "practical"
    LAB = "lab"
    OTHER = "other"

class Teacher(Base):
    """Преподаватель."""
    __tablename__ = "teachers"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(255), nullable=False)
    login = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime, nullable=True)

    temp_passwords = relationship(
        "TempTeacherPassword",
        back_populates="teacher",
        cascade="all, delete-orphan"
    )
    group_links = relationship(
        "GroupTeacher",
        back_populates="teacher",
        cascade="all, delete-orphan"
    )
    subject_links = relationship(
        "SubjectTeacher",
        back_populates="teacher",
        cascade="all, delete-orphan"
    )
    owned_groups = relationship(
        "Group",
        back_populates="owner_teacher",
        foreign_keys="Group.owner_teacher_id"
    )
    owned_subjects = relationship(
        "Subject",
        back_populates="owner_teacher",
        foreign_keys="Subject.owner_teacher_id"
    )

    groups = relationship(
        "Group",
        secondary="group_teachers",
        back_populates="teachers",
        viewonly=True
    )

    subjects = relationship(
        "Subject",
        secondary="subject_teachers",
        back_populates="teachers",
        viewonly=True
    )

    __table_args__ = (
        Index("idx_teacher_active", "is_active"),
        Index("idx_teacher_deleted", "deleted_at"),
    )

class Group(Base):
    """Учебная группа."""
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False, index=True)
    registration_code = Column(String(50), nullable=True, index=True)
    registration_enabled = Column(Boolean, default=False, nullable=False)
    registration_method = Column(
        Enum(RegistrationMethod),
        default=RegistrationMethod.AUTO,
        nullable=False
    )
    owner_teacher_id = Column(
        Integer,
        ForeignKey("teachers.id", ondelete="SET NULL"),
        nullable=True
    )
    created_by_admin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    owner_teacher = relationship(
        "Teacher",
        foreign_keys=[owner_teacher_id],
        back_populates="owned_groups"
    )
    students = relationship(
        "Student",
        back_populates="group",
        cascade="all, delete-orphan"
    )
    group_subjects = relationship(
        "GroupSubject",
        back_populates="group",
        cascade="all, delete-orphan"
    )
    teacher_links = relationship(
        "GroupTeacher",
        back_populates="group",
        cascade="all, delete-orphan"
    )

    subjects = relationship(
        "Subject",
        secondary="group_subjects",
        back_populates="groups",
        viewonly=True,
        overlaps="group_subjects"
    )

    teachers = relationship(
        "Teacher",
        secondary="group_teachers",
        back_populates="groups",
        viewonly=True,
        overlaps="teacher_links"
    )

    __table_args__ = (
        Index("idx_group_active", "is_active"),
        Index("idx_group_deleted", "deleted_at"),
        Index("idx_group_owner", "owner_teacher_id"),
        Index("idx_group_reg_code", "registration_code"),
    )

class Student(Base):
    """Студент."""
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(255), nullable=False)
    login = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    group_id = Column(
        Integer,
        ForeignKey("groups.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    registered = Column(Boolean, default=False, nullable=False)
    registration_code = Column(String(50), nullable=True, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    group = relationship("Group", back_populates="students")
    submissions = relationship(
        "Submission",
        back_populates="student",
        cascade="all, delete-orphan"
    )
    temp_password = relationship(
        "TempPassword",
        back_populates="student",
        cascade="all, delete-orphan",
        uselist=False
    )

    __table_args__ = (
        Index("idx_student_active", "is_active"),
        Index("idx_student_deleted", "deleted_at"),
        Index("idx_student_group", "group_id"),
        Index("idx_student_reg_code", "registration_code"),
    )

class Subject(Base):
    """Дисциплина."""
    __tablename__ = "subjects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    attestation_type = Column(
        Enum(AttestationType),
        default=AttestationType.NONE,
        nullable=False,
    )
    owner_teacher_id = Column(
        Integer,
        ForeignKey("teachers.id", ondelete="SET NULL"),
        nullable=True
    )
    created_by_admin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    owner_teacher = relationship(
        "Teacher",
        foreign_keys=[owner_teacher_id],
        back_populates="owned_subjects"
    )
    group_subjects = relationship(
        "GroupSubject",
        back_populates="subject",
        cascade="all, delete-orphan"
    )

    groups = relationship(
        "Group",
        secondary="group_subjects",
        back_populates="subjects",
        viewonly=True,
        overlaps="group_subjects"
    )
    materials = relationship(
        "Material",
        back_populates="subject",
        cascade="all, delete-orphan"
    )
    assignments = relationship(
        "Assignment",
        back_populates="subject",
        cascade="all, delete-orphan"
    )
    teacher_links = relationship(
        "SubjectTeacher",
        back_populates="subject",
        cascade="all, delete-orphan"
    )

    teachers = relationship(
        "Teacher",
        secondary="subject_teachers",
        back_populates="subjects",
        viewonly=True,
        overlaps="teacher_links"
    )

    __table_args__ = (
        Index("idx_subject_active", "is_active"),
        Index("idx_subject_deleted", "deleted_at"),
        Index("idx_subject_owner", "owner_teacher_id"),
        UniqueConstraint("name", "deleted_at", name="uq_subject_name_deleted"),
    )

class GroupTeacher(Base):
    """Назначение преподавателей группе."""
    __tablename__ = "group_teachers"

    group_id = Column(
        Integer,
        ForeignKey("groups.id", ondelete="CASCADE"),
        primary_key=True
    )
    teacher_id = Column(
        Integer,
        ForeignKey("teachers.id", ondelete="CASCADE"),
        primary_key=True
    )
    assigned_at = Column(DateTime, server_default=func.now(), nullable=False)
    assigned_by = Column(String(100), nullable=True)

    group = relationship("Group", back_populates="teacher_links")
    teacher = relationship("Teacher", back_populates="group_links")

    __table_args__ = (
        Index("idx_group_teacher_group", "group_id"),
        Index("idx_group_teacher_teacher", "teacher_id"),
    )

class SubjectTeacher(Base):
    """Назначение преподавателей дисциплине."""
    __tablename__ = "subject_teachers"

    subject_id = Column(
        Integer,
        ForeignKey("subjects.id", ondelete="CASCADE"),
        primary_key=True
    )
    teacher_id = Column(
        Integer,
        ForeignKey("teachers.id", ondelete="CASCADE"),
        primary_key=True
    )
    assigned_at = Column(DateTime, server_default=func.now(), nullable=False)
    assigned_by = Column(String(100), nullable=True)

    subject = relationship("Subject", back_populates="teacher_links")
    teacher = relationship("Teacher", back_populates="subject_links")

    __table_args__ = (
        Index("idx_subject_teacher_subject", "subject_id"),
        Index("idx_subject_teacher_teacher", "teacher_id"),
    )

class GroupSubject(Base):
    """Связь группы с дисциплиной."""
    __tablename__ = "group_subjects"

    group_id = Column(
        Integer,
        ForeignKey("groups.id", ondelete="CASCADE"),
        primary_key=True
    )
    subject_id = Column(
        Integer,
        ForeignKey("subjects.id", ondelete="CASCADE"),
        primary_key=True
    )
    assigned_at = Column(DateTime, server_default=func.now(), nullable=False)
    assigned_by = Column(String(100), nullable=True)

    group = relationship("Group", back_populates="group_subjects")
    subject = relationship("Subject", back_populates="group_subjects")

    __table_args__ = (
        Index("idx_group_subject_group", "group_id"),
        Index("idx_group_subject_subject", "subject_id"),
    )

class Material(Base):
    """Учебные материалы."""
    __tablename__ = "materials"

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(
        Integer,
        ForeignKey("subjects.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    material_type = Column(
        Enum(MaterialType),
        default=MaterialType.OTHER,
        nullable=False
    )
    files = Column(Text, nullable=False)
    order = Column(Integer, default=0, nullable=False)
    is_published = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime, nullable=True)

    subject = relationship("Subject", back_populates="materials")

    __table_args__ = (
        Index("idx_material_subject", "subject_id"),
        Index("idx_material_deleted", "deleted_at"),
        Index("idx_material_order", "subject_id", "order"),
    )

class Assignment(Base):
    """Задания."""
    __tablename__ = "assignments"

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(
        Integer,
        ForeignKey("subjects.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    requirements = Column(Text, nullable=True)
    files = Column(Text, nullable=True)
    deadline = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    subject = relationship("Subject", back_populates="assignments")
    submissions = relationship(
        "Submission",
        back_populates="assignment",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_assignment_subject", "subject_id"),
        Index("idx_assignment_deleted", "deleted_at"),
        Index("idx_assignment_active", "is_active"),
        Index("idx_assignment_deadline", "deadline"),
    )

class Submission(Base):
    """Сданные работы."""
    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(
        Integer,
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    assignment_id = Column(
        Integer,
        ForeignKey("assignments.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    files = Column(Text, nullable=True)
    github_link = Column(Text, nullable=True)
    submitted_at = Column(DateTime, server_default=func.now(), nullable=False)
    grade = Column(Integer, nullable=True)
    status = Column(
        Enum(SubmissionStatus),
        default=SubmissionStatus.SUBMITTED,
        nullable=False
    )
    feedback = Column(Text, nullable=True)
    resubmission_count = Column(Integer, default=0, nullable=False)
    resubmitted_at = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True)

    student = relationship("Student", back_populates="submissions")
    assignment = relationship("Assignment", back_populates="submissions")
    analysis = relationship(
        "CodeAnalysis",
        back_populates="submission",
        cascade="all, delete-orphan",
        uselist=False
    )

    __table_args__ = (
        CheckConstraint('grade IN (2, 3, 4, 5)', name='valid_grade'),
        Index("idx_submission_student", "student_id"),
        Index("idx_submission_assignment", "assignment_id"),
        Index("idx_submission_status", "status"),
        Index("idx_submission_deleted", "deleted_at"),
        Index("idx_submission_grade", "grade"),
    )

class CodeAnalysis(Base):
    """Анализ кода."""
    __tablename__ = "code_analysis"

    id = Column(Integer, primary_key=True, index=True)
    submission_id = Column(
        Integer,
        ForeignKey("submissions.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True
    )
    style_issues = Column(Integer, default=0, nullable=False)
    ai_generated_probability = Column(Float, default=0.0, nullable=False)
    plagiarism_match_id = Column(Integer, nullable=True)
    suggested_grade = Column(Integer, nullable=True)
    analysis_status = Column(
        Enum(AnalysisStatus),
        default=AnalysisStatus.PENDING,
        nullable=False
    )
    error_message = Column(Text, nullable=True)
    ai_suggestions = Column(Text, nullable=True)
    analyzed_at = Column(DateTime, server_default=func.now(), nullable=False)

    submission = relationship("Submission", back_populates="analysis")

    __table_args__ = (
        CheckConstraint('suggested_grade IN (2, 3, 4, 5)', name='valid_suggested_grade'),
        Index("idx_analysis_submission", "submission_id"),
        Index("idx_analysis_status", "analysis_status"),
    )

class TempPassword(Base):
    """Временные пароли студентов (для первого входа)."""
    __tablename__ = "temp_passwords"

    student_id = Column(
        Integer,
        ForeignKey("students.id", ondelete="CASCADE"),
        primary_key=True
    )
    password = Column(String(255), nullable=False)
    is_used = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    student = relationship("Student", back_populates="temp_password")

    __table_args__ = (
        Index("idx_temp_password_used", "is_used"),
    )

class TempTeacherPassword(Base):
    """Временные пароли преподавателей (для первого входа)."""
    __tablename__ = "temp_teacher_passwords"

    teacher_id = Column(
        Integer,
        ForeignKey("teachers.id", ondelete="CASCADE"),
        primary_key=True
    )
    password = Column(String(255), nullable=False)
    is_used = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    teacher = relationship("Teacher", back_populates="temp_passwords")

    __table_args__ = (
        Index("idx_temp_teacher_used", "is_used"),
    )
