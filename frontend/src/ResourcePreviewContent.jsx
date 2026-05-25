import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import mammoth from 'mammoth';
import * as XLSX from 'xlsx';
import './ResourcePreviewContent.css';

const API_BASE_URL = process.env.REACT_APP_API_URL || '';
const MAX_SHEET_PREVIEW_ROWS = 200;

function buildResourceUrl(path, queryKey, queryValue) {
    return `${API_BASE_URL}${path}?${queryKey}=${encodeURIComponent(queryValue)}`;
}

function normalizeSheetRows(rawRows) {
    const rows = Array.isArray(rawRows) ? rawRows.slice(0, MAX_SHEET_PREVIEW_ROWS) : [];
    let maxColumnCount = 0;
    rows.forEach((row) => {
        if (Array.isArray(row)) {
            maxColumnCount = Math.max(maxColumnCount, row.length);
        }
    });
    if (maxColumnCount <= 0) {
        maxColumnCount = 1;
    }
    return rows.map((row) => {
        const source = Array.isArray(row) ? row : [];
        return Array.from({ length: maxColumnCount }, (_, index) => {
            const value = source[index];
            return value === null || value === undefined ? '' : String(value);
        });
    });
}

function ResourcePreviewContent({
    detailData,
    accessQueryKey,
    accessQueryValue,
    loadingText = '加载预览中...',
    emptyText = '暂无可预览内容',
    unsupportedText = '当前文件类型不支持在线预览，请下载查看。',
    sheetRowLimitNotice = `仅展示前 ${MAX_SHEET_PREVIEW_ROWS} 行`,
}) {
    const [binaryLoading, setBinaryLoading] = useState(false);
    const [binaryError, setBinaryError] = useState('');
    const [docxHtml, setDocxHtml] = useState('');
    const [sheetRowsMap, setSheetRowsMap] = useState({});
    const [sheetNames, setSheetNames] = useState([]);
    const [activeSheet, setActiveSheet] = useState('');

    const previewMode = detailData?.preview_mode || '';

    useEffect(() => {
        let cancelled = false;

        const resetState = () => {
            setBinaryError('');
            setDocxHtml('');
            setSheetRowsMap({});
            setSheetNames([]);
            setActiveSheet('');
        };

        const loadBinaryPreview = async () => {
            if (!detailData || !['docx', 'sheet'].includes(previewMode)) {
                resetState();
                setBinaryLoading(false);
                return;
            }

            resetState();
            setBinaryLoading(true);
            try {
                const downloadUrl = buildResourceUrl(detailData.download_url, accessQueryKey, accessQueryValue);
                const response = await axios.get(downloadUrl, { responseType: 'arraybuffer' });
                if (cancelled) return;

                if (previewMode === 'docx') {
                    const result = await mammoth.convertToHtml({ arrayBuffer: response.data });
                    if (cancelled) return;
                    setDocxHtml(result.value || '');
                    return;
                }

                const workbook = XLSX.read(response.data, { type: 'array' });
                const names = Array.isArray(workbook.SheetNames) ? workbook.SheetNames : [];
                const nextMap = {};
                names.forEach((name) => {
                    const sheet = workbook.Sheets[name];
                    const rawRows = XLSX.utils.sheet_to_json(sheet, {
                        header: 1,
                        raw: false,
                        defval: '',
                    });
                    nextMap[name] = normalizeSheetRows(rawRows);
                });

                setSheetNames(names);
                setSheetRowsMap(nextMap);
                setActiveSheet(names[0] || '');
            } catch (error) {
                if (!cancelled) {
                    setBinaryError(error?.message || '预览加载失败');
                }
            } finally {
                if (!cancelled) {
                    setBinaryLoading(false);
                }
            }
        };

        loadBinaryPreview();
        return () => {
            cancelled = true;
        };
    }, [detailData, previewMode, accessQueryKey, accessQueryValue]);

    const activeSheetRows = useMemo(() => {
        if (!activeSheet) return [];
        return sheetRowsMap[activeSheet] || [];
    }, [activeSheet, sheetRowsMap]);

    if (!detailData) {
        return <div className="resource-preview-empty">{emptyText}</div>;
    }

    if (previewMode === 'pdf') {
        return (
            <iframe
                title={`resource-preview-${detailData.id}`}
                src={buildResourceUrl(detailData.preview_url, accessQueryKey, accessQueryValue)}
                className="resource-preview-frame"
            />
        );
    }

    if (['text', 'markdown'].includes(previewMode)) {
        return <pre className="resource-text-preview">{detailData.preview_text || emptyText}</pre>;
    }

    if (previewMode === 'docx') {
        if (binaryLoading) {
            return <div className="resource-preview-empty">{loadingText}</div>;
        }
        if (binaryError) {
            return <div className="resource-preview-empty">{binaryError}</div>;
        }
        if (!docxHtml) {
            return <div className="resource-preview-empty">{emptyText}</div>;
        }
        return (
            <div
                className="resource-docx-preview"
                dangerouslySetInnerHTML={{ __html: docxHtml }}
            />
        );
    }

    if (previewMode === 'sheet') {
        if (binaryLoading) {
            return <div className="resource-preview-empty">{loadingText}</div>;
        }
        if (binaryError) {
            return <div className="resource-preview-empty">{binaryError}</div>;
        }
        if (!sheetNames.length || !activeSheetRows.length) {
            return <div className="resource-preview-empty">{emptyText}</div>;
        }

        const [headerRow, ...bodyRows] = activeSheetRows;
        return (
            <div className="resource-sheet-preview">
                <div className="resource-sheet-toolbar">
                    <div className="resource-sheet-tabs">
                        {sheetNames.map((name) => (
                            <button
                                key={name}
                                type="button"
                                className={`resource-sheet-tab ${activeSheet === name ? 'active' : ''}`}
                                onClick={() => setActiveSheet(name)}
                            >
                                {name}
                            </button>
                        ))}
                    </div>
                    <span className="resource-sheet-note">{sheetRowLimitNotice}</span>
                </div>
                <div className="resource-sheet-table-wrap">
                    <table className="resource-sheet-table">
                        <thead>
                            <tr>
                                {headerRow.map((cell, index) => (
                                    <th key={`head-${index}`}>{cell || `列${index + 1}`}</th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {bodyRows.map((row, rowIndex) => (
                                <tr key={`row-${rowIndex}`}>
                                    {row.map((cell, cellIndex) => (
                                        <td key={`cell-${rowIndex}-${cellIndex}`}>{cell}</td>
                                    ))}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>
        );
    }

    return <div className="resource-preview-empty">{unsupportedText}</div>;
}

export default ResourcePreviewContent;
