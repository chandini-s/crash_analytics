pipeline {
  agent any
  options { timestamps(); ansiColor('xterm') }

  // Keep parameters (you'll see the page, but values are remembered)
  parameters {
    string(name: 'DEVICES',    defaultValue: '2411FD1LG0A2', description: 'Serial(s)/IP(s); space or comma separated')
    text  (name: 'AUTH',   defaultValue: '',             description: 'Auth header text (paste exact)')
    text  (name: 'COOKIE', defaultValue: '',             description: 'Cookie header text (do NOT trim)')
    // No TEST_TARGET param. We default to mtr in CI if empty.
  }

  environment {
    SEVEN_ZIP = "C:\\Program Files\\7-Zip\\7z.exe"
  }

  stages {
    stage('Checkout') { steps { checkout scm } }

    stage('Python venv & deps (Windows)') {
      steps {
        bat '''
          if not exist .venv\\Scripts\\python.exe (
            py -3 -m venv .venv
          )
          .venv\\Scripts\\python.exe -m pip install --upgrade pip
          if exist requirements.txt (
            .venv\\Scripts\\pip.exe install -r requirements.txt
          ) else (
            .venv\\Scripts\\pip.exe install pytest pytest-html requests
          )
        '''
      }
    }

    stage('Reset reports dir') {
      steps {
        bat '''
          if exist reports rmdir /s /q reports
          mkdir reports
          if exist downloaded_bugreports rmdir /s /q downloaded_bugreports
          mkdir downloaded_bugreports
          if not exist config mkdir config
        '''
      }
    }

    stage('Write runtime config from PARAMETERS') {
      steps {
        // Preserve exact text (don’t lose semicolons, spaces, etc.)
        script {
          writeFile file: 'config/auth.txt',    text: (params.AUTH_TXT   ?: '')
          writeFile file: 'config/cookie.txt',  text: (params.COOKIE_TXT ?: '')
          writeFile file: 'config/devices.txt', text: (params.DEVICES    ?: '')
        }
        bat """
          echo === Using parameter values ===
          echo DEVICES=%DEVICES%
        """
      }
    }

    stage('Run tests (one suite, one time)') {
      steps {
        bat """
          setlocal enabledelayedexpansion

          rem ---- pass params to runner ----
          set DEVICES=%DEVICES%
          set SEVEN_ZIP=%SEVEN_ZIP%

          rem ---- CI-safe default to avoid 'auto' branch on Jenkins ----
          if "%TEST_TARGET%"=="" if not "%JENKINS_URL%"=="" set TEST_TARGET=mtr

          echo DEVICES=%DEVICES%
          echo TEST_TARGET=%TEST_TARGET%
          .venv\\Scripts\\python.exe tests_run.py
        """
      }
    }

    stage('Select latest report') {
      steps {
        bat """
          setlocal EnableDelayedExpansion
          set LATEST=
          for /f "delims=" %%F in ('dir /b /a:-d /o:-d reports\\report_*.html') do (
            set LATEST=%%F
            goto :after
          )
          :after
          if not "!LATEST!"=="" copy /Y "reports\\!LATEST!" "reports\\index.html" >nul
        """
      }
    }
  }

  post {
    always {
      // harmless if you don't emit XML; keeps console tidy
      junit allowEmptyResults: true, testResults: 'reports/**/*.xml'

      // archive all html + zips (debugarchives, downloaded bugreports)
      archiveArtifacts artifacts: 'reports/*.html, downloaded_bugreports/**/*.zip, **/debugarchive_*.zip',
                       fingerprint: true, onlyIfSuccessful: false

      // Publish just the latest report (index.html).
      // Requires the "HTML Publisher" plugin.
      script {
        catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
          publishHTML(target: [
            reportDir: 'reports',
            reportFiles: 'index.html',
            reportName: 'Crash Analytics – Latest HTML Report',
            keepAll: true,
            allowMissing: true,
            alwaysLinkToLastBuild: true
          ])
        }
      }
    }
  }
}
