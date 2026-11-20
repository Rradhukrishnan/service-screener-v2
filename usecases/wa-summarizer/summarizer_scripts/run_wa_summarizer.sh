#!/bin/bash
# Quadra Recon Well-Architected Summarizer
# A tool to analyze Quadra Recon output and generate Well-Architected Framework analysis reports
# Usage: ./run_wa_summarizer.sh -d <service-screener-dir> [-o <output-dir>]

set -e

# Color definitions for output formatting
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default settings
SUMMARIZER_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT_DIR="$(cd "${SUMMARIZER_SCRIPT_DIR}/.." && pwd)"
DEFAULT_OUTPUT_DIR="${PROJECT_ROOT_DIR}/output"
PROMPT_FILE="${PROJECT_ROOT_DIR}/src/prompt/wa_summarizer.md"
KIRO_PROMPTS_DIR="${HOME}/.kiro/prompts"

# Variable to store prompt file path for cleanup
prompt_file=""

# Cleanup function
cleanup() {
    if [ -n "$prompt_file" ] && [ -f "$prompt_file" ]; then
        echo ""
        echo -e "${YELLOW}🧹 Cleaning up temporary prompt file...${NC}"
        rm -f "$prompt_file"
        if [ $? -eq 0 ]; then
            echo -e "${GREEN}✅ Temporary prompt file removed.${NC}"
        fi
    fi
}

# Set trap to cleanup on exit
trap cleanup EXIT

# Help function
show_help() {
    echo -e "${BLUE}Quadra Recon Well-Architected Summarizer${NC}"
    echo ""
    echo "A tool to analyze Quadra Recon output and generate Well-Architected Framework analysis reports."
    echo ""
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  -d, --dir DIRECTORY     Quadra Recon results directory (required)"
    echo "  -o, --output DIRECTORY  Output directory for reports (default: ./output)"
    echo "  -h, --help              Display this help message"
    echo ""
    echo "Example:"
    echo "  $0 -d /path/to/service-screener-results"
    echo "  $0 --dir ./screener-output --output ./my-reports"
}

# Main function
main() {
    local service_screener_dir=""
    local output_dir="$DEFAULT_OUTPUT_DIR"

    # Parse command-line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            -d|--dir)
                service_screener_dir="$2"
                shift 2
                ;;
            -o|--output)
                output_dir="$2"
                shift 2
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            *)
                echo -e "${RED}❌ Unknown option: $1${NC}"
                show_help
                exit 1
                ;;
        esac
    done

    # Check if service_screener_dir is provided
    if [ -z "$service_screener_dir" ]; then
        echo -e "${RED}❌ Quadra Recon directory is required.${NC}"
        show_help
        exit 1
    fi

    # Validate that the Quadra Recon directory exists
    if [ ! -d "$service_screener_dir" ]; then
        echo -e "${RED}❌ Quadra Recon directory does not exist: $service_screener_dir${NC}"
        exit 1
    fi

    # Check for required Quadra Recon files and structure
    # Look for at least one account directory
    account_dirs=$(find "$service_screener_dir" -maxdepth 1 -type d -not -path "$service_screener_dir" | wc -l)
    if [ "$account_dirs" -eq 0 ]; then
        echo -e "${RED}❌ No account directories found in Quadra Recon directory.${NC}"
        echo -e "${YELLOW}ℹ️ Quadra Recon directory should contain at least one account directory.${NC}"
        exit 1
    fi

    # Check for index.html in at least one account directory
    index_files=$(find "$service_screener_dir" -maxdepth 2 -name "index.html" | wc -l)
    if [ "$index_files" -eq 0 ]; then
        echo -e "${RED}❌ No index.html files found in Quadra Recon directory.${NC}"
        echo -e "${YELLOW}ℹ️ Quadra Recon directory should contain index.html files in account directories.${NC}"
        exit 1
    fi

    # Check for CPFindings.html in at least one account directory
    findings_files=$(find "$service_screener_dir" -maxdepth 2 -name "CPFindings.html" | wc -l)
    if [ "$findings_files" -eq 0 ]; then
        echo -e "${RED}❌ No CPFindings.html files found in Quadra Recon directory.${NC}"
        echo -e "${YELLOW}ℹ️ Quadra Recon directory should contain CPFindings.html files in account directories.${NC}"
        exit 1
    fi

    # Create output directory if it doesn't exist
    if [ ! -d "$output_dir" ]; then
        echo -e "${YELLOW}ℹ️ Creating output directory: $output_dir${NC}"
        mkdir -p "$output_dir"
        if [ $? -ne 0 ]; then
            echo -e "${RED}❌ Failed to create output directory: $output_dir${NC}"
            exit 1
        fi
    fi

    # Check if output directory is writable
    if [ ! -w "$output_dir" ]; then
        echo -e "${RED}❌ Output directory is not writable: $output_dir${NC}"
        exit 1
    fi

    # Create Kiro prompts directory if it doesn't exist
    if [ ! -d "$KIRO_PROMPTS_DIR" ]; then
        echo -e "${YELLOW}ℹ️ Creating Kiro prompts directory: $KIRO_PROMPTS_DIR${NC}"
        mkdir -p "$KIRO_PROMPTS_DIR"
        if [ $? -ne 0 ]; then
            echo -e "${RED}❌ Failed to create Kiro prompts directory: $KIRO_PROMPTS_DIR${NC}"
            exit 1
        fi
    fi

    # Generate timestamp for unique filenames
    timestamp=$(date +"%Y%m%d_%H%M%S")
    report_filename="wa_summary_report_${timestamp}.html"
    report_path="${output_dir}/${report_filename}"

    echo -e "${GREEN}📄 Report will be saved in: $report_path${NC}"
    echo -e "${YELLOW}🚀 Starting Quadra Recon Well-Architected Framework Summarizer...${NC}"
    echo ""

    # Check for Kiro CLI
    if ! command -v kiro-cli --version &> /dev/null; then
        echo -e "${RED}❌ Kiro CLI is not installed.${NC}"
        echo -e "${YELLOW}ℹ️ Please install Kiro CLI before running this tool.${NC}"
        exit 1
    fi

    # Check for AWS credentials
    if ! aws sts get-caller-identity &> /dev/null; then
        echo -e "${RED}❌ AWS credentials are not configured.${NC}"
        echo -e "${YELLOW}ℹ️ Please configure AWS credentials using 'aws configure' before running this tool.${NC}"
        exit 1
    fi

    # Check if prompt file exists
    if [ ! -f "$PROMPT_FILE" ]; then
        echo -e "${RED}❌ Prompt file does not exist: $PROMPT_FILE${NC}"
        exit 1
    fi

    echo -e "${YELLOW}📊 Analyzing Quadra Recon data...${NC}"
    
    # Prepare the prompt with the Quadra Recon directory path
    prompt_filename="summarizer-wa-prompt-${timestamp}"
    prompt_file="${KIRO_PROMPTS_DIR}/${prompt_filename}.md"
    sed "s|{SERVICE_SCREENER_DIR}|$service_screener_dir|g" "$PROMPT_FILE" > "$prompt_file"

    # Prepare the prompt with the default output directory path
    sed -i.bak "s|{DEFAULT_OUTPUT_DIR}|$output_dir|g" "$prompt_file" && rm -f "${prompt_file}.bak"
    
    # Send the prompt to Kiro CLI and save the output
    echo -e "${YELLOW}🤖 Sending request to Kiro...${NC}"

    kiro-cli settings chat.defaultModel claude-sonnet-4.5
    kiro-cli chat --trust-all-tools @${prompt_filename}
    
    # Check if the command was successful
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Quadra Recon Well-Architected Summarizer completed!${NC}"
    else
        echo -e "${RED}❌ Failed to generate report.${NC}"
        exit 1
    fi
}

# Execute the main function
main "$@"