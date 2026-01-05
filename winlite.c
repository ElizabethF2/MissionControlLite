#include <stdio.h>
#include <stdlib.h>

#include <Windows.h>
#include <winhttp.h>
#include <wincrypt.h>

#pragma comment(lib, "Winhttp.lib")
#pragma comment(lib, "Crypt32.lib")

#define ERROR_TOO_FEW_ARGS       1
#define ERROR_MISSING_CERT       2
#define ERROR_CERT_TOO_SMALL     3

void run_str(wchar_t* cmd)
{
  STARTUPINFOW si;
  PROCESS_INFORMATION pi;
  ZeroMemory(&si, sizeof(si));
  si.cb = sizeof(si);
  ZeroMemory(&pi, sizeof(pi));
  BOOL res = CreateProcessW(NULL, cmd, NULL, NULL, FALSE, 0, NULL, NULL, &si, &pi);
#if DEBUG
  printf("CreateProcessW( %ws ) -> %d\n", cmd, res);
#endif
  WaitForSingleObject(pi.hProcess, INFINITE);
  CloseHandle(pi.hProcess);
  CloseHandle(pi.hThread);
}

static void* s_cert_buf = NULL;
static DWORD s_cert_size = 0;

void cert_callback(
  HINTERNET request,
  DWORD_PTR dwContext,
  DWORD dwInternetStatus,
  LPVOID lpvStatusInformation,
  DWORD dwStatusInformationLength
)
{
#if DEBUG
  printf("dwInternetStatus = %d\n", dwInternetStatus);
#endif

  PCCERT_CONTEXT ctx = NULL;
  DWORD ctxlen = sizeof(ctx);
  BOOL succeeded = WinHttpQueryOption(
    request,
    WINHTTP_OPTION_SERVER_CERT_CONTEXT,
    &ctx,
    &ctxlen
  );

#if DEBUG
  printf("GetLastError -> %d\n", GetLastError());
  printf("WinHttpQueryOption -> %d\n", succeeded);
  printf("ctx = %p\n", ctx);
#endif

  DWORD server_cert_size = (ctx) ? ctx->cbCertEncoded : 0;
  int cmp = (s_cert_size == server_cert_size) ?
            memcmp(s_cert_buf, ctx->pbCertEncoded, s_cert_size) :
            1;
  CertFreeCertificateContext(ctx);

#if DEBUG
  printf("cert_size = %d\n", s_cert_size);
  printf("server_cert_size = %d\n", server_cert_size);
  printf("cmp = %d\n", cmp);
#endif

  if (succeeded && cmp != 0)
  {
    CloseHandle(request);
  }
}

int wmain(int argc, wchar_t *argv[])
{
  if (argc < 8) {
#if DEBUG
  printf("usage: %ws [delay] [timeout] [certificate] [host] [port] [path] [server script] [network fixer script]\n", argv[0]);
#endif
    return ERROR_TOO_FEW_ARGS;
  }

  unsigned long delay = wcstoul(argv[1], NULL, 10);
  unsigned long timeout = wcstoul(argv[2], NULL, 10);
  unsigned long port = wcstoul(argv[5], NULL, 10);

#if DEBUG
  printf("delay = %lu\n", delay);
  printf("timeout = %lu\n", timeout);
  printf("port = %lu\n", port);
#endif

  HINTERNET session = WinHttpOpen(
    NULL,
    WINHTTP_ACCESS_TYPE_AUTOMATIC_PROXY,
    WINHTTP_NO_PROXY_NAME,
    WINHTTP_NO_PROXY_BYPASS,
    0
  );

#if DEBUG
  printf("session = %p\n", session);
#endif

  BOOL res = WinHttpSetTimeouts(
    session,
    timeout,
    timeout,
    timeout,
    timeout
  );

#if DEBUG
  printf("WinHttpSetTimeouts -> %d\n", res);
#endif

  {
    HANDLE fh = CreateFileW(
      argv[3],
      GENERIC_READ,
      FILE_SHARE_READ,
      NULL,
      OPEN_EXISTING,
      0,
      NULL
    );

#if DEBUG
  printf("CreateFileW -> %p\n", fh);
#endif
    
    if (fh == INVALID_HANDLE_VALUE)
      return ERROR_MISSING_CERT;

    s_cert_size = GetFileSize(fh, NULL);

#if DEBUG
  printf("GetFileSize -> %d\n", s_cert_size);
#endif

    if (s_cert_size < 1)
      return ERROR_CERT_TOO_SMALL;
  
    {
      s_cert_buf = malloc(s_cert_size);
      
#if DEBUG
  printf("malloc -> %p\n", s_cert_buf);
#endif

      DWORD remaining = s_cert_size;
      void* cbuf = s_cert_buf;
      while (remaining)
      {
        DWORD read = 0;
        res = ReadFile(fh, cbuf, remaining, &read, NULL);
        remaining -= read;
        ((BYTE*)cbuf) += read;

#if DEBUG
  printf("ReadFile -> %d (read %d)\n", res, read);
#endif
      }

      CloseHandle(fh);
    }
  }

  while(1)
  {
    Sleep(delay);

    HINTERNET connection = WinHttpConnect(session, argv[4], port, 0);

#if DEBUG
  printf("connection = %p\n", connection);
#endif

    HINTERNET request = WinHttpOpenRequest(
      connection,
      NULL,
      argv[6],
      NULL,
      WINHTTP_NO_REFERER,
      WINHTTP_DEFAULT_ACCEPT_TYPES,
      WINHTTP_FLAG_SECURE
    );

#if DEBUG
  printf("request = %p\n", request);
#endif

  DWORD flags = SECURITY_FLAG_IGNORE_UNKNOWN_CA;
  BOOL res = WinHttpSetOption(
    request,
    WINHTTP_OPTION_SECURITY_FLAGS,
    &flags,
    sizeof(flags)
  );

#if DEBUG
  printf("WinHttpSetOption -> %d\n", res);
#endif

  WINHTTP_STATUS_CALLBACK cb_res = WinHttpSetStatusCallback(
    request,
    (WINHTTP_STATUS_CALLBACK)cert_callback,
    WINHTTP_CALLBACK_FLAG_SEND_REQUEST,
    (DWORD_PTR)NULL
  );
  
#if DEBUG
  printf("WinHttpSetStatusCallback -> %p\n", cb_res);
#endif

    res = WinHttpSendRequest(
      request,
      WINHTTP_NO_ADDITIONAL_HEADERS,
      0,
      WINHTTP_NO_REQUEST_DATA,
      0,
      0,
      (DWORD_PTR) NULL
    );

#if DEBUG
  printf("WinHttpSendRequest -> %d (error: %d)\n", res, GetLastError());
#endif

    res = WinHttpReceiveResponse(request, NULL);

#if DEBUG
  printf("WinHttpReceiveResponse -> %d\n", res);
#endif

    int char_count = 0;
    BOOL succeeded = FALSE;
    DWORD remaining = 0;
    do
    {
      res = WinHttpQueryDataAvailable(request, &remaining);

#if DEBUG
  printf("WinHttpQueryDataAvailable -> %d\n", res);
  printf("remaining = %d\n", remaining);
#endif

      char buf[4096];
      DWORD read;
      succeeded = WinHttpReadData(request, &buf, 4096, &read);
      for (int i = 0; i < read; ++i)
      {
        char c = buf[i];
        if (c != ' ' && c != '\n' && c != '\t' && c != '\r')
        {
          ++char_count;
#if DEBUG
          if (isprint(c) && !isspace(c))
          {
            printf("Received: %c\n", c);
          }
          else
          {
            printf("Received: (char %d)\n", c);
          }
#endif
        }
      }
    }
    while(remaining);

#if DEBUG
  printf("char_count = %d\n", char_count);
  printf("WinHttpReadData -> %d\n", succeeded);
#endif
    
    if (!succeeded)
    {
      run_str(argv[8]);
    }
    else if (char_count > 2)
    {
      run_str(argv[7]);
    }

    WinHttpCloseHandle(request);
    WinHttpCloseHandle(connection);
  }

  return 0;
}
