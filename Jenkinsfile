pipeline {
  // Run on whatever node you choose. For Mac-only, set: agent { label 'mac-mini' }
  agent any
  // No parameters block here — set DEVICE/AUTH/COOKIE in the job's Configure page.

  environment {
    SEVEN_ZIP = ''  // we'll auto-detect per-OS below
  }

  stages {
    stage('Checkout') { steps { checkout scm } }

    stage('Python venv & deps') {
      steps {
        script {
          if (isUnix()) {
            sh '''
              set -euo pipefail
              python3 -m venv .venv
              . .venv/bin/activate
              python -m pip install --upgrade pip
              if [ -f requirements.txt ]; then
                pip install -r requirements.txt
              else
                pip install pytest pytest-html requests
              fi
            '''
          } else {
            bat '''
              if not exist .venv\\Scripts\\python.exe ( py -3 -m venv .venv )
              .venv\\Scripts\\python.exe -m pip install --upgrade pip
              if exist requirements.txt (
                .venv\\Scripts\\pip.exe install -r requirements.txt
              ) else (
                .venv\\Scripts\\pip.exe install pytest pytest-html requests
              )
            '''
          }
        }
      }
    }

    stage('Prep workspace dirs') {
      steps {
        script {
          if (isUnix()) {
            sh '''
              set -e
              rm -rf "$WORKSPACE/reports" "$WORKSPACE/downloaded_bugreports" "$WORKSPACE/config"
              mkdir -p "$WORKSPACE/reports" "$WORKSPACE/downloaded_bugreports" "$WORKSPACE/config"
            '''
          } else {
            bat """
              if exist "%WORKSPACE%\\reports" rmdir /s /q "%WORKSPACE%\\reports"
              if exist "%WORKSPACE%\\downloaded_bugreports" rmdir /s /q "%WORKSPACE%\\downloaded_bugreports"
              if not exist "%WORKSPACE%\\reports" mkdir "%WORKSPACE%\\reports"
              if not exist "%WORKSPACE%\\downloaded_bugreports" mkdir "%WORKSPACE%\\downloaded_bugreports"
              if not exist "%WORKSPACE%\\config" mkdir "%WORKSPACE%\\config"
            """
          }
        }
      }
    }

    stage('Write runtime config from Jenkins parameters') {
      steps {
        // These env vars come from the job's Configure → parameters you saved
        script {
          writeFile file: 'config/auth.txt',    text: (env.AUTH   ?: '')
          writeFile file: 'config/cookie.txt',  text: (env.COOKIE ?: '')
          writeFile file: 'config/devices.txt', text: (env.DEVICE ?: '')
        }
      }
    }

    stage('Run tests (focused-app decides the suite)') {
      steps {
        script {
          if (isUnix()) {
            sh '''
              set -e
              : "${DEVICE:?Set DEVICE in job Configure → This project is parameterized}"
              export DEVICE="${DEVICE}"

              # Tell Python to put the report inside the Jenkins workspace
              export REPORTS_DIR="$WORKSPACE/reports"
              export REPORT_FILE="index.html"

              # Find 7-zip if available (Homebrew p7zip installs 7zz)
              export SEVEN_ZIP="${SEVEN_ZIP:-$(command -v 7zz || command -v 7z || true)}"

              . .venv/bin/activate
              python3 tests_run.py
            '''
          } else {
           bat """
               if "%DEVICE%"=="" (
               echo ERROR: Set DEVICE in job Configure ^> This project is parameterized & exit /b 2
               )
              set REPORTS_DIR=%WORKSPACE%\\reports
              set REPORT_FILE=index.html
              if not exist "%REPORTS_DIR%" mkdir "%REPORTS_DIR%"

              rem Auto-detect 7-Zip if not provided
              if "%SEVEN_ZIP%"=="" if exist "%ProgramFiles%\\7-Zip\\7z.exe" set SEVEN_ZIP=%ProgramFiles%\\7-Zip\\7z.exe
              if "%SEVEN_ZIP%"=="" if exist "%ProgramFiles(x86)%\\7-Zip\\7z.exe" set SEVEN_ZIP=%ProgramFiles(x86)%\\7-Zip\\7z.exe

              .venv\\Scripts\\python.exe tests_run.py
              if errorlevel 1 exit /b 1
            """
          }
        }
      }
    }
  }

  post {
    always {
      junit allowEmptyResults: true, testResults: 'reports/**/*.xml'
      archiveArtifacts artifacts: 'reports/*.html, downloaded_bugreports/**/*.zip, **/debugarchive_*.zip',
                       fingerprint: true, onlyIfSuccessful: false
      // If HTML Publisher plugin is missing, this won't fail the whole build
      script {
        catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
          publishHTML(target: [
            reportDir: 'reports',
            reportFiles: 'index.html',
            reportName: 'Crash Analytics – Latest HTML Report',
            keepAll: true, allowMissing: true, alwaysLinkToLastBuild: true
          ])
        }
      }
    }
  }
}