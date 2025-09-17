pipeline {
  agent any

  // Keep parameters (Jenkins will show the page but remember last values)
  parameters {
    string(name: 'DEVICE',    defaultValue: '', description: 'Serial/IP or IP:port')
    text  (name: 'AUTH',      defaultValue: '', description: 'Auth header text (paste exact)')
    text  (name: 'COOKIE',    defaultValue: '', description: 'Cookie header text (do NOT trim)')
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
        // <<< FIX: use the actual parameter names >>>
        script {
          writeFile file: 'config/auth.txt',    text: (params.AUTH   ?: '')
          writeFile file: 'config/cookie.txt',  text: (params.COOKIE ?: '')
          writeFile file: 'config/devices.txt', text: (params.DEVICE ?: '')
        }
        bat """
          echo === Using parameter values ===
          echo DEVICE=%DEVICE%
        """
      }
    }

    stage('Run tests (one suite, one time)') {
      steps {
        bat """
          setlocal EnableDelayedExpansion
          rem pass the Jenkins parameter straight through
          set DEVICE=%DEVICE%
          set SEVEN_ZIP=%SEVEN_ZIP%

          echo DEVICE=%DEVICE%
          .venv\\Scripts\\python.exe tests_run.py
          if errorlevel 1 exit /b 1
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
      junit allowEmptyResults: true, testResults: 'reports/**/*.xml'

      archiveArtifacts artifacts: 'reports/*.html, downloaded_bugreports/**/*.zip, **/debugarchive_*.zip',
                       fingerprint: true, onlyIfSuccessful: false

      // Publish just the latest report (index.html). Guard so missing plugin won't fail build.
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
