import os
from dotenv import load_dotenv
load_dotenv(verbose=True)

import requests
import io
from typing import BinaryIO, Any
import tempfile
from dataclasses import dataclass

from src.logger import logger

# Try to import markitdown and its internal modules
MARKITDOWN_AVAILABLE = False
try:
    from markitdown import MarkItDown
    from markitdown.converters import PdfConverter
    from markitdown.converters import AudioConverter
    from markitdown.converters._pdf_converter import _dependency_exc_info
    from markitdown.converters._exiftool import exiftool_metadata
    from markitdown._stream_info import StreamInfo
    from markitdown._base_converter import DocumentConverterResult
    from markitdown._exceptions import MissingDependencyException, MISSING_DEPENDENCY_MESSAGE
    MARKITDOWN_AVAILABLE = True
except ImportError as e:
    logger.warning(f"markitdown not fully available: {e}")
    # Fallback classes
    MarkItDown = None
    PdfConverter = None
    AudioConverter = None
    _dependency_exc_info = None
    exiftool_metadata = None
    StreamInfo = None
    MissingDependencyException = Exception
    MISSING_DEPENDENCY_MESSAGE = "markitdown not installed"
    
    @dataclass
    class DocumentConverterResult:
        """Fallback dataclass when markitdown is not available."""
        markdown: str = ""
        title: str = ""

# Try to import pdfminer
try:
    import pdfminer
    import pdfminer.high_level
    PDFMINER_AVAILABLE = True
except ImportError:
    PDFMINER_AVAILABLE = False
    pdfminer = None

# Try to import litellm transcription
try:
    from litellm import transcription
    LITELLM_AVAILABLE = True
except ImportError:
    LITELLM_AVAILABLE = False
    transcription = None

# Lazy import model_manager to avoid circular imports
def _get_model_manager():
    from src.models import model_manager
    return model_manager

# Optional import for PDF table extraction
try:
    import camelot
    CAMELOT_AVAILABLE = True
except ImportError:
    CAMELOT_AVAILABLE = False
    camelot = None


def read_tables_from_stream(file_stream):
    if not CAMELOT_AVAILABLE:
        logger.warning("camelot-py not installed, PDF table extraction not available")
        return []
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as temp_pdf:
        temp_pdf.write(file_stream.read())
        temp_pdf.flush()
        tables = camelot.read_pdf(temp_pdf.name, flavor="lattice")
        return tables

def transcribe_audio(file_stream, audio_format):
    model_manager = _get_model_manager()
    
    if "whisper" in model_manager.registed_models:
        # Use the Whisper model for transcription
        model = model_manager.registed_models["whisper"]
        result = model(
            file_stream=file_stream,
        )
    elif LITELLM_AVAILABLE and transcription:
        response = transcription(model="gpt-4o-transcribe", file=file_stream).json()
        result = response.get("text", "No transcription available.")
    else:
        result = "Audio transcription not available - whisper model not configured and litellm not installed."

    return result

# Custom converters - only defined if markitdown is available
if MARKITDOWN_AVAILABLE and AudioConverter is not None:
    class AudioWhisperConverter(AudioConverter):

        def convert(
                self,
                file_stream: BinaryIO,
                stream_info: StreamInfo,
                **kwargs: Any,  # Options to pass to the converter
        ) -> DocumentConverterResult:
            md_content = ""

            # Add metadata
            metadata = exiftool_metadata(
                file_stream, exiftool_path=kwargs.get("exiftool_path")
            )
            if metadata:
                for f in [
                    "Title",
                    "Artist",
                    "Author",
                    "Band",
                    "Album",
                    "Genre",
                    "Track",
                    "DateTimeOriginal",
                    "CreateDate",
                    # "Duration", -- Wrong values when read from memory
                    "NumChannels",
                    "SampleRate",
                    "AvgBytesPerSec",
                    "BitsPerSample",
                ]:
                    if f in metadata:
                        md_content += f"{f}: {metadata[f]}\n"

            # Figure out the audio format for transcription
            if stream_info.extension == ".wav" or stream_info.mimetype == "audio/x-wav":
                audio_format = "wav"
            elif stream_info.extension == ".mp3" or stream_info.mimetype == "audio/mpeg":
                audio_format = "mp3"
            elif (
                    stream_info.extension in [".mp4", ".m4a"]
                    or stream_info.mimetype == "video/mp4"
            ):
                audio_format = "mp4"
            else:
                audio_format = None

            # Transcribe
            if audio_format:
                try:
                    transcript = transcribe_audio(file_stream, audio_format=audio_format)
                    if transcript:
                        md_content += "\n\n### Audio Transcript:\n" + transcript
                except MissingDependencyException:
                    pass

            # Return the result
            return DocumentConverterResult(markdown=md_content.strip())
else:
    AudioWhisperConverter = None

if MARKITDOWN_AVAILABLE and PdfConverter is not None:
    class PdfWithTableConverter(PdfConverter):
        def convert(
            self,
            file_stream: BinaryIO,
            stream_info: StreamInfo,
            **kwargs: Any,  # Options to pass to the converter
        ) -> DocumentConverterResult:
            # Check the dependencies
            if _dependency_exc_info is not None:
                raise MissingDependencyException(
                    MISSING_DEPENDENCY_MESSAGE.format(
                        converter=type(self).__name__,
                        extension=".pdf",
                        feature="pdf",
                    )
                ) from _dependency_exc_info[
                    1
                ].with_traceback(  # type: ignore[union-attr]
                    _dependency_exc_info[2]
                )

            assert isinstance(file_stream, io.IOBase)  # for mypy

            tables = read_tables_from_stream(file_stream)
            if not tables or (hasattr(tables, 'n') and tables.n == 0):
                if PDFMINER_AVAILABLE:
                    return DocumentConverterResult(
                        markdown=pdfminer.high_level.extract_text(file_stream),
                    )
                else:
                    return DocumentConverterResult(markdown="PDF extraction not available")
            else:
                num_tables = tables.n if hasattr(tables, 'n') else len(tables)
                markdown_content = pdfminer.high_level.extract_text(file_stream) if PDFMINER_AVAILABLE else ""
                table_content = ""
                for i in range(num_tables):
                    table = tables[i].df
                    table_content += f"Table {i + 1}:\n" + table.to_markdown(index=False) + "\n\n"
                markdown_content += "\n\n" + table_content
                return DocumentConverterResult(
                    markdown=markdown_content,
                )
else:
    PdfWithTableConverter = None

class MarkitdownConverter():
    def __init__(self,
                 use_llm: bool = False,
                 model_id: str = None,
                 timeout: int = 30):

        self.timeout = timeout
        self.use_llm = use_llm
        self.model_id = model_id
        
        if not MARKITDOWN_AVAILABLE:
            logger.warning("markitdown not available, MarkitdownConverter will have limited functionality")
            self.client = None
            return

        if use_llm:
            model_manager = _get_model_manager()
            client = model_manager.registed_models(model_id).http_client
            self.client = MarkItDown(
                enable_plugins=True,
                llm_client=client,
                llm_model=model_id,
            )
        else:
            self.client = MarkItDown(
                enable_plugins=True,
            )

        removed_converters = [
            c for c in [PdfConverter, AudioConverter] if c is not None
        ]

        if removed_converters:
            self.client._converters = [
                converter for converter in self.client._converters
                if not isinstance(converter.converter, tuple(removed_converters))
            ]
        
        # Register custom converters if available
        if PdfWithTableConverter is not None:
            self.client.register_converter(PdfWithTableConverter())
        if AudioWhisperConverter is not None:
            self.client.register_converter(AudioWhisperConverter())

    def convert(self, source: str, **kwargs: Any):
        if self.client is None:
            logger.error("MarkitdownConverter not available - markitdown package not installed")
            return DocumentConverterResult(
                markdown=f"Error: markitdown not installed, cannot convert {source}",
                title="Conversion Error"
            )
        try:
            result = self.client.convert(
                source,
                **kwargs)
            return result
        except Exception as e:
            logger.error(f"Error during conversion: {e}")
            return None