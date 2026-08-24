
from pydantic import BaseModel, Field, validator
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum

class RegistrationMethod(str, Enum):
    """Registrationmethod."""
    AUTO = "auto"
    SELF = "self"

class SubmissionStatus(str, Enum):
    """Submissionstatus."""
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    REVISION = "revision"
    REJECTED = "rejected"

class AnalysisStatus(str, Enum):
    """Analysisstatus."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"

class MaterialType(str, Enum):
    """Materialtype."""
    LECTURE = "lecture"
    PRACTICAL = "practical"
    LAB = "lab"
    OTHER = "other"

class TeacherBase(BaseModel):
    """Teacherbase."""
    full_name: str = Field(..., max_length=255)
    login: str = Field(..., max_length=100)
    is_active: bool = True

class TeacherCreate(TeacherBase):
    """Teachercreate."""
    password: str = Field(..., min_length=6)

class TeacherUpdate(BaseModel):
    """Teacherupdate."""
    full_name: Optional[str] = Field(None, max_length=255)
    login: Optional[str] = Field(None, max_length=100)
    is_active: Optional[bool] = None
    password: Optional[str] = Field(None, min_length=6)

class TeacherResponse(TeacherBase):
    """Teacherresponse."""
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    temp_password: Optional[str] = None

    class Config:
        """Config."""
        from_attributes = True

class StudentBase(BaseModel):
    """Studentbase."""
    full_name: str = Field(..., max_length=255)
    login: str = Field(..., max_length=100)
    group_id: Optional[int] = None
    is_active: bool = True

class StudentCreate(StudentBase):
    """Studentcreate."""
    password: str = Field(..., min_length=6)

class StudentUpdate(BaseModel):
    """Studentupdate."""
    full_name: Optional[str] = Field(None, max_length=255)
    login: Optional[str] = Field(None, max_length=100)
    is_active: Optional[bool] = None
    group_id: Optional[int] = None
    password: Optional[str] = Field(None, min_length=6)

class StudentResponse(StudentBase):
    """Studentresponse."""
    id: int
    registered: bool
    registration_code: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    temp_password: Optional[str] = None
    group_name: Optional[str] = None

    class Config:
        """Config."""
        from_attributes = True

class GroupBase(BaseModel):
    """Groupbase."""
    name: str = Field(..., max_length=255)
    registration_method: RegistrationMethod = RegistrationMethod.AUTO
    registration_enabled: bool = False
    is_active: bool = True

class GroupCreate(GroupBase):
    """Groupcreate."""
    teacher_ids: Optional[List[int]] = Field(default_factory=list)
    subject_ids: Optional[List[int]] = Field(default_factory=list)
    students: Optional[List[str]] = Field(default_factory=list)

class GroupUpdate(BaseModel):
    """Groupupdate."""
    name: Optional[str] = Field(None, max_length=255)
    registration_method: Optional[RegistrationMethod] = None
    registration_enabled: Optional[bool] = None
    registration_code: Optional[str] = None
    is_active: Optional[bool] = None
    teacher_ids: Optional[List[int]] = None
    subject_ids: Optional[List[int]] = None
    students: Optional[List[str]] = None

class GroupResponse(GroupBase):
    """Groupresponse."""
    id: int
    registration_code: Optional[str] = None
    owner_teacher_id: Optional[int] = None
    owner_teacher_name: Optional[str] = None
    created_by_admin: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    students_count: int = 0
    teachers: List[TeacherResponse] = []
    subjects: List['SubjectResponse'] = []
    students: List[StudentResponse] = []

    class Config:
        """Config."""
        from_attributes = True

class SubjectBase(BaseModel):
    """Subjectbase."""
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    is_active: bool = True

class SubjectCreate(SubjectBase):
    """Subjectcreate."""
    teacher_ids: Optional[List[int]] = Field(default_factory=list)

class SubjectUpdate(BaseModel):
    """Subjectupdate."""
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    is_active: Optional[bool] = None
    teacher_ids: Optional[List[int]] = None

class SubjectResponse(SubjectBase):
    """Subjectresponse."""
    id: int
    owner_teacher_id: Optional[int] = None
    owner_teacher_name: Optional[str] = None
    created_by_admin: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    teachers: List[TeacherResponse] = []
    groups: List[GroupResponse] = []
    materials_count: int = 0
    assignments_count: int = 0

    class Config:
        """Config."""
        from_attributes = True

class MaterialBase(BaseModel):
    """Materialbase."""
    subject_id: int
    title: str = Field(..., max_length=255)
    description: Optional[str] = None
    material_type: MaterialType = MaterialType.OTHER
    order: int = 0
    is_published: bool = True

class MaterialCreate(MaterialBase):
    """Materialcreate."""
    files: List[Dict[str, Any]] = Field(default_factory=list)

class MaterialUpdate(BaseModel):
    """Materialupdate."""
    title: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    material_type: Optional[MaterialType] = None
    order: Optional[int] = None
    is_published: Optional[bool] = None
    files: Optional[List[Dict[str, Any]]] = None

class MaterialResponse(MaterialBase):
    """Materialresponse."""
    id: int
    files: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: datetime
    updated_at: Optional[datetime] = None
    subject_name: Optional[str] = None

    class Config:
        """Config."""
        from_attributes = True

class AssignmentBase(BaseModel):
    """Assignmentbase."""
    subject_id: int
    title: str = Field(..., max_length=255)
    description: Optional[str] = None
    requirements: Optional[str] = None
    deadline: Optional[datetime] = None
    is_active: bool = True

class AssignmentCreate(AssignmentBase):
    """Assignmentcreate."""
    files: Optional[List[Dict[str, Any]]] = None
    group_ids: List[int] = Field(default_factory=list)

class AssignmentUpdate(BaseModel):
    """Assignmentupdate."""
    title: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    requirements: Optional[str] = None
    deadline: Optional[datetime] = None
    is_active: Optional[bool] = None
    files: Optional[List[Dict[str, Any]]] = None
    group_ids: Optional[List[int]] = None

class AssignmentResponse(AssignmentBase):
    """Assignmentresponse."""
    id: int
    files: Optional[List[Dict[str, Any]]] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    subject_name: Optional[str] = None
    submissions_count: int = 0
    graded_count: int = 0
    groups: List[GroupResponse] = []

    class Config:
        """Config."""
        from_attributes = True

class SubmissionBase(BaseModel):
    """Submissionbase."""
    student_id: int
    assignment_id: int
    status: SubmissionStatus = SubmissionStatus.SUBMITTED

class SubmissionCreate(SubmissionBase):
    """Submissioncreate."""
    files: Optional[List[Dict[str, Any]]] = None
    github_link: Optional[str] = None

class SubmissionUpdate(BaseModel):
    """Submissionupdate."""
    status: Optional[SubmissionStatus] = None
    grade: Optional[int] = Field(None, ge=2, le=5)
    feedback: Optional[str] = None

class SubmissionResponse(SubmissionBase):
    """Submissionresponse."""
    id: int
    files: Optional[List[Dict[str, Any]]] = None
    github_link: Optional[str] = None
    grade: Optional[int] = None
    feedback: Optional[str] = None
    resubmission_count: int = 0
    resubmitted_at: Optional[datetime] = None
    submitted_at: datetime
    student_name: Optional[str] = None
    assignment_title: Optional[str] = None
    group_name: Optional[str] = None

    class Config:
        """Config."""
        from_attributes = True

class CodeAnalysisBase(BaseModel):
    """Codeanalysisbase."""
    submission_id: int
    style_issues: int = 0
    ai_generated_probability: float = 0.0
    suggested_grade: Optional[int] = Field(None, ge=2, le=5)
    analysis_status: AnalysisStatus = AnalysisStatus.PENDING
    error_message: Optional[str] = None
    ai_suggestions: Optional[Dict[str, Any]] = None

class CodeAnalysisCreate(CodeAnalysisBase):
    """Codeanalysiscreate."""
    pass

class CodeAnalysisUpdate(BaseModel):
    """Codeanalysisupdate."""
    style_issues: Optional[int] = None
    ai_generated_probability: Optional[float] = None
    plagiarism_match_id: Optional[int] = None
    suggested_grade: Optional[int] = Field(None, ge=2, le=5)
    analysis_status: Optional[AnalysisStatus] = None
    error_message: Optional[str] = None
    ai_suggestions: Optional[Dict[str, Any]] = None

class CodeAnalysisResponse(CodeAnalysisBase):
    """Codeanalysisresponse."""
    id: int
    plagiarism_match_id: Optional[int] = None
    analyzed_at: datetime
    student_name: Optional[str] = None
    assignment_title: Optional[str] = None

    class Config:
        """Config."""
        from_attributes = True

class GroupTeacherResponse(BaseModel):
    """Groupteacherresponse."""
    group_id: int
    teacher_id: int
    assigned_at: datetime
    assigned_by: Optional[str] = None

    class Config:
        """Config."""
        from_attributes = True

class SubjectTeacherResponse(BaseModel):
    """Subjectteacherresponse."""
    subject_id: int
    teacher_id: int
    assigned_at: datetime
    assigned_by: Optional[str] = None

    class Config:
        """Config."""
        from_attributes = True

class GroupSubjectResponse(BaseModel):
    """Groupsubjectresponse."""
    group_id: int
    subject_id: int
    assigned_at: datetime
    assigned_by: Optional[str] = None

    class Config:
        """Config."""
        from_attributes = True

class LoginRequest(BaseModel):
    """Loginrequest."""
    login: str
    password: str

class RegistrationRequest(BaseModel):
    """Registrationrequest."""
    full_name: str = Field(..., max_length=255)
    login: str = Field(..., max_length=100)
    password: str = Field(..., min_length=6)
    registration_code: str

class UploadResponse(BaseModel):
    """Uploadresponse."""
    status: str
    message: str
    submission_id: int
    files: List[Dict[str, Any]] = Field(default_factory=list)

class AnalysisRequest(BaseModel):
    """Analysisrequest."""
    assignment_id: int
    group_id: Optional[int] = None

class AnalysisResult(BaseModel):
    """Analysisresult."""
    submission_id: int
    student_name: str
    style_issues: int
    ai_generated_probability: float
    plagiarism_match: Optional[str] = None
    recommendations: List[str] = Field(default_factory=list)
    suggested_grade: Optional[int] = None

class PaginatedResponse(BaseModel):
    """Paginatedresponse."""
    items: List[Any]
    total: int
    page: int
    page_size: int
    pages: int

class DashboardStats(BaseModel):
    """Dashboardstats."""
    total_teachers: int
    total_students: int
    total_groups: int
    total_subjects: int
    total_assignments: int
    total_submissions: int
    graded_submissions: int
    pending_submissions: int

class TempPasswordResponse(BaseModel):
    """Temppasswordresponse."""
    student_id: int
    password: str
    is_used: bool
    created_at: datetime

    class Config:
        """Config."""
        from_attributes = True

class TempTeacherPasswordResponse(BaseModel):
    """Tempteacherpasswordresponse."""
    teacher_id: int
    password: str
    is_used: bool
    created_at: datetime

    class Config:
        """Config."""
        from_attributes = True

SubjectResponse.model_rebuild()
GroupResponse.model_rebuild()
AssignmentResponse.model_rebuild()
