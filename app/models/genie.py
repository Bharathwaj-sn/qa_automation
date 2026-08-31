from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GenieConfigurationError(ValueError):
    pass


class GenieSerializedSpaceModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class GenieColumnConfig(GenieSerializedSpaceModel):
    column_name: str
    enable_format_assistance: bool | None = None
    enable_entity_matching: bool | None = None


class GenieTableConfig(GenieSerializedSpaceModel):
    identifier: str
    column_configs: list[GenieColumnConfig] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_column_names(self):
        column_names = [column.column_name for column in self.column_configs]
        if len(column_names) != len(set(column_names)):
            raise ValueError("column_configs must not contain duplicate column_name values.")
        return self


class GenieDataSources(GenieSerializedSpaceModel):
    tables: list[GenieTableConfig] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_table_identifiers(self):
        identifiers = [table.identifier for table in self.tables]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("tables must not contain duplicate identifier values.")
        return self


class GenieTextInstruction(GenieSerializedSpaceModel):
    id: str
    content: list[str] = Field(default_factory=list)


class GenieExampleQuestionSql(GenieSerializedSpaceModel):
    id: str
    question: list[str] = Field(default_factory=list)
    sql: list[str] = Field(default_factory=list)
    usage_guidance: list[str] = Field(default_factory=list)


class GenieInstructions(GenieSerializedSpaceModel):
    text_instructions: list[GenieTextInstruction] = Field(default_factory=list)
    example_question_sqls: list[GenieExampleQuestionSql] = Field(default_factory=list)


class GenieSampleQuestion(GenieSerializedSpaceModel):
    id: str
    question: list[str] = Field(default_factory=list)


class GenieConfig(GenieSerializedSpaceModel):
    sample_questions: list[GenieSampleQuestion] = Field(default_factory=list)


class GenieSerializedSpace(GenieSerializedSpaceModel):
    version: int
    config: GenieConfig = Field(default_factory=GenieConfig)
    data_sources: GenieDataSources = Field(default_factory=GenieDataSources)
    instructions: GenieInstructions = Field(default_factory=GenieInstructions)

    @model_validator(mode="after")
    def validate_version(self):
        if self.version != 2:
            raise ValueError(f"Unsupported Genie serialized space version: {self.version}.")
        return self

    @classmethod
    def from_serialized_space(cls, serialized_space: str) -> GenieSerializedSpace:
        return cls.model_validate_json(serialized_space)

    def to_serialized_space(self) -> str:
        return self.model_dump_json()

    def canonicalize(self) -> GenieSerializedSpace:
        canonical = self.model_copy(deep=True)
        canonical.data_sources.tables.sort(key=lambda table: table.identifier)
        for table in canonical.data_sources.tables:
            table.column_configs.sort(key=lambda column: column.column_name)
        canonical.instructions.text_instructions.sort(key=lambda instruction: instruction.id)
        canonical.instructions.example_question_sqls.sort(key=lambda example: example.id)
        canonical.config.sample_questions.sort(key=lambda question: question.id)
        return canonical

    def add_table(self, table: GenieTableConfig) -> GenieSerializedSpace:
        if any(existing.identifier == table.identifier for existing in self.data_sources.tables):
            raise GenieConfigurationError(f"Table already exists: {table.identifier}.")

        updated = self.model_copy(deep=True)
        updated.data_sources.tables.append(table.model_copy(deep=True))
        return updated

    def remove_table(self, identifier: str) -> GenieSerializedSpace:
        if not any(table.identifier == identifier for table in self.data_sources.tables):
            raise GenieConfigurationError(f"Table does not exist: {identifier}.")

        updated = self.model_copy(deep=True)
        updated.data_sources.tables = [
            table for table in updated.data_sources.tables if table.identifier != identifier
        ]
        return updated

    def update_table(self, table: GenieTableConfig) -> GenieSerializedSpace:
        if not any(existing.identifier == table.identifier for existing in self.data_sources.tables):
            raise GenieConfigurationError(f"Table does not exist: {table.identifier}.")

        updated = self.model_copy(deep=True)
        updated.data_sources.tables = [
            table.model_copy(deep=True) if existing.identifier == table.identifier else existing
            for existing in updated.data_sources.tables
        ]
        return updated

    def update_instructions(
        self,
        text_instructions: list[GenieTextInstruction],
    ) -> GenieSerializedSpace:
        updated = self.model_copy(deep=True)
        updated.instructions.text_instructions = [
            instruction.model_copy(deep=True) for instruction in text_instructions
        ]
        return updated

    def add_sql_example(self, example: GenieExampleQuestionSql) -> GenieSerializedSpace:
        updated = self.model_copy(deep=True)
        updated.instructions.example_question_sqls.append(example.model_copy(deep=True))
        return updated


class GenieSpace(BaseModel):
    space_id: str
    title: str | None = None
    description: str | None = None
    warehouse_id: str | None = None
    parent_path: str | None = None
    serialized_space: GenieSerializedSpace | None = None


class GenieSpaceSummary(BaseModel):
    space_id: str
    title: str | None = None
    description: str | None = None
    warehouse_id: str | None = None
    parent_path: str | None = None


class GenieSpaceListResponse(BaseModel):
    spaces: list[GenieSpaceSummary] = Field(default_factory=list)
    next_page_token: str | None = None


class GenieSpaceUpdateRequest(BaseModel):
    serialized_space: GenieSerializedSpace


class GenieSQLGeneration(BaseModel):
    space_id: str
    conversation_id: str
    message_id: str
    sql: str


class GenieConversationMessageRequest(BaseModel):
    content: str = Field(min_length=1)